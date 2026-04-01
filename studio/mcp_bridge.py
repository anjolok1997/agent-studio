"""
MCP Bridge — Connect agent tools to real MCP servers.

When configured, replaces simulated tool responses with real MCP tool calls.
Falls back to simulated tools when MCP is not configured.

Requires: pip install mcp
"""

import asyncio
import json
from pathlib import Path

import yaml

from .permissions import PermissionGuard, ToolRisk, TOOL_RISK_MAP
from .events import EventEmitter

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False


# Default risk levels for common MCP tool patterns
MCP_RISK_DEFAULTS = {
    "read": ToolRisk.SAFE,
    "list": ToolRisk.SAFE,
    "search": ToolRisk.SAFE,
    "get": ToolRisk.SAFE,
    "query": ToolRisk.SAFE,
    "write": ToolRisk.SENSITIVE,
    "create": ToolRisk.SENSITIVE,
    "update": ToolRisk.SENSITIVE,
    "send": ToolRisk.SENSITIVE,
    "delete": ToolRisk.DANGEROUS,
    "drop": ToolRisk.DANGEROUS,
    "execute": ToolRisk.DANGEROUS,
    "run": ToolRisk.DANGEROUS,
    "deploy": ToolRisk.DANGEROUS,
    "shell": ToolRisk.DANGEROUS,
}


def _infer_risk(tool_name: str) -> ToolRisk:
    """Infer risk level from a tool name based on common patterns."""
    name_lower = tool_name.lower()
    for keyword, risk in MCP_RISK_DEFAULTS.items():
        if keyword in name_lower:
            return risk
    return ToolRisk.SENSITIVE  # Default to sensitive for unknown tools


class MCPServer:
    """Represents a single MCP server connection."""

    def __init__(self, name: str, config: dict):
        self.name = name
        self.transport = config.get("transport", "stdio")
        self.command = config.get("command")
        self.args = config.get("args", [])
        self.env = config.get("env", {})
        self.url = config.get("url")
        self.tool_risks = config.get("tool_risks", {})
        self.sandbox = config.get("sandbox")  # "docker" or None
        self.tools: list[dict] = []
        self._session = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected


class MCPBridge:
    """
    Bridges agent tool calls to real MCP servers.

    Usage:
        bridge = MCPBridge(Path("mcp_config.yaml"), permissions)
        bridge.connect_all()

        # Check if a tool is available via MCP
        if bridge.has_tool("read_file"):
            result = bridge.call_tool("read_file", {"path": "/tmp/test.txt"}, "data-engineer")

        bridge.disconnect_all()
    """

    def __init__(self, config_path: Path, permissions: PermissionGuard, emitter: EventEmitter = None):
        if not HAS_MCP:
            raise ImportError(
                "MCP package not installed. Install with: pip install mcp"
            )

        self.permissions = permissions
        self.emitter = emitter or EventEmitter()
        self.servers: dict[str, MCPServer] = {}
        self.connected_servers: list[str] = []
        self._tool_to_server: dict[str, str] = {}

        # Load config
        config = yaml.safe_load(config_path.read_text())
        for name, server_config in config.get("servers", {}).items():
            self.servers[name] = MCPServer(name, server_config)

    def connect_all(self):
        """Connect to all configured MCP servers and discover tools."""
        for name, server in self.servers.items():
            try:
                sandbox_label = " [Docker]" if server.sandbox == "docker" else ""
                self._connect_server(server)
                self.connected_servers.append(name)
                self.emitter.emit("mcp.connected", {
                    "server": name,
                    "tools": len(server.tools),
                    "sandboxed": server.sandbox == "docker",
                })
                print(f"  MCP: Connected to '{name}'{sandbox_label} ({len(server.tools)} tools)")
            except Exception as e:
                print(f"  MCP: Failed to connect to '{name}': {e}")

    def _connect_server(self, server: MCPServer):
        """Connect to a single MCP server and discover its tools."""
        if server.transport == "stdio":
            # Use Docker sandbox if configured
            if server.sandbox == "docker":
                command, args = self._get_docker_command(server)
            else:
                command = server.command
                args = server.args

            tools = asyncio.run(self._connect_stdio_with(
                command, args, server.env if server.sandbox != "docker" else None,
            ))
            server.tools = tools
            server._connected = True

            # Register tools with permission system
            for tool in tools:
                tool_name = tool["name"]
                self._tool_to_server[tool_name] = server.name

                # Use explicit risk from config, or infer from name
                if tool_name in server.tool_risks:
                    risk = ToolRisk(server.tool_risks[tool_name])
                else:
                    risk = _infer_risk(tool_name)
                TOOL_RISK_MAP[tool_name] = risk

    def _get_docker_command(self, server: MCPServer) -> tuple[str, list[str]]:
        """Build Docker command for sandboxed MCP server execution."""
        from .mcp_sandbox import get_docker_command
        raw_config = {
            "args": server.args,
            "env": server.env,
        }
        docker_cmd = get_docker_command(server.name, raw_config)
        if not docker_cmd:
            # Fallback to direct execution
            return server.command, server.args
        # docker_cmd is a full command list, split into command + args
        return docker_cmd[0], docker_cmd[1:]

    async def _connect_stdio_with(self, command: str, args: list,
                                   env: dict = None) -> list[dict]:
        """Connect to a stdio MCP server and list its tools."""
        params = StdioServerParameters(
            command=command,
            args=args,
            env=env if env else None,
        )

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()

                tools = []
                for tool in result.tools:
                    tools.append({
                        "name": tool.name,
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema if hasattr(tool, "inputSchema") else {
                            "type": "object",
                            "properties": {},
                        },
                    })
                return tools

    def discover_tools(self) -> list[dict]:
        """Return all tools from all connected MCP servers in Anthropic format."""
        tools = []
        for server in self.servers.values():
            if server.connected:
                tools.extend(server.tools)
        return tools

    def has_tool(self, name: str) -> bool:
        """Check if any MCP server provides this tool."""
        return name in self._tool_to_server

    def call_tool(self, name: str, inputs: dict, agent_type: str) -> str:
        """
        Call an MCP tool. Checks permissions first.
        Returns the result string or an error message.
        """
        # Permission check happens in Station._run_tool before this is called,
        # but we double-check here for safety
        allowed, reason = self.permissions.check(name, inputs)
        if not allowed:
            return f"[BLOCKED] {reason}"

        server_name = self._tool_to_server.get(name)
        if not server_name:
            return f"[MCP ERROR] No server provides tool '{name}'"

        server = self.servers[server_name]

        self.emitter.emit("mcp.tool_called", {
            "server": server_name,
            "tool": name,
            "agent": agent_type,
        })

        try:
            result = asyncio.run(self._call_tool_async(server, name, inputs))
            return result
        except Exception as e:
            error_msg = f"[MCP ERROR] Tool '{name}' failed: {str(e)}"
            self.emitter.emit("mcp.tool_error", {
                "server": server_name,
                "tool": name,
                "error": str(e),
            })
            return error_msg

    async def _call_tool_async(self, server: MCPServer, name: str, inputs: dict) -> str:
        """Execute a tool call against an MCP server."""
        if server.transport == "stdio":
            if server.sandbox == "docker":
                command, args = self._get_docker_command(server)
            else:
                command, args = server.command, server.args
            params = StdioServerParameters(
                command=command,
                args=args,
                env=server.env if server.sandbox != "docker" else None,
            )

            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(name, arguments=inputs)

                    # Extract text from result
                    if hasattr(result, "content"):
                        texts = []
                        for block in result.content:
                            if hasattr(block, "text"):
                                texts.append(block.text)
                        return "\n".join(texts) if texts else str(result)
                    return str(result)

        return f"[MCP ERROR] Unsupported transport: {server.transport}"

    def disconnect_all(self):
        """Clean up all server connections."""
        self.connected_servers = []
        self._tool_to_server = {}
        for server in self.servers.values():
            server._connected = False
            server.tools = []
