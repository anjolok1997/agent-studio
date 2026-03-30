"""
Station — Worker agent execution.

Each worker is a specialist agent that runs a focused subtask
using tools (research, draft_output, flag_blocker).
"""

from pathlib import Path
from anthropic import Anthropic

from .events import EventEmitter
from .permissions import PermissionGuard
from .agent_loader import AgentLoader

WORKER_TOOLS = [
    {
        "name": "research",
        "description": "Research or deeply analyze a topic relevant to your subtask.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
    {
        "name": "draft_output",
        "description": "Produce a concrete artifact: plan, spec, code outline, checklist, etc.",
        "input_schema": {
            "type": "object",
            "properties": {"content": {"type": "string"}},
            "required": ["content"],
        },
    },
    {
        "name": "flag_blocker",
        "description": "Signal that this subtask cannot proceed and explain why.",
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
]


# Shared loader instance — created on first use
_default_loader: AgentLoader = None


def _get_loader() -> AgentLoader:
    global _default_loader
    if _default_loader is None:
        _default_loader = AgentLoader()
    return _default_loader


def load_agent_prompt(agent_type: str) -> str:
    """Load a specialist system prompt by agent ID."""
    return _get_loader().load_prompt(agent_type)


def list_available_agents() -> list[str]:
    """Return all available agent IDs (library + local)."""
    return _get_loader().list_agent_ids()


def get_agent_loader() -> AgentLoader:
    """Get the shared AgentLoader instance."""
    return _get_loader()


class Station:
    """Runs a specialist worker agent on a single subtask."""

    def __init__(self, client: Anthropic, worker_model: str = "claude-haiku-4-5-20251001",
                 emitter: EventEmitter = None, permissions: PermissionGuard = None,
                 mcp_bridge=None):
        self.client = client
        self.worker_model = worker_model
        self.emitter = emitter or EventEmitter()
        self.permissions = permissions or PermissionGuard()
        self.mcp_bridge = mcp_bridge
        self.artifacts: list[dict] = []

    def _run_tool(self, name: str, inputs: dict, agent_type: str) -> str:
        # Check permissions before executing any tool
        allowed, reason = self.permissions.check(name, inputs)
        if not allowed:
            self.emitter.emit("worker.tool_blocked", {"agent": agent_type, "tool": name, "reason": reason})
            print(f"      [{agent_type}] {name} -> BLOCKED: {reason}")
            return f"[BLOCKED] {reason}"

        # Try MCP bridge first for real tool execution
        if self.mcp_bridge and self.mcp_bridge.has_tool(name):
            return self.mcp_bridge.call_tool(name, inputs, agent_type)

        # Built-in tools — these produce real output without MCP
        if name == "research":
            self.emitter.emit("worker.tool_called", {"agent": agent_type, "tool": name, "topic": inputs["topic"]})
            return self._do_research(inputs["topic"], agent_type)
        if name == "draft_output":
            self.artifacts.append({"agent": agent_type, "content": inputs["content"]})
            self.emitter.emit("worker.tool_called", {"agent": agent_type, "tool": name, "chars": len(inputs["content"])})
            return f"[{agent_type}] Draft saved ({len(inputs['content'])} chars)."
        if name == "flag_blocker":
            self.emitter.emit("worker.blocked", {"agent": agent_type, "reason": inputs["reason"]})
            return f"[ESCALATION:BLOCKER] {agent_type}: {inputs['reason']}"
        return f"Unknown tool: {name}"

    def _do_research(self, topic: str, agent_type: str) -> str:
        """Actually research a topic using the model's knowledge."""
        system = load_agent_prompt(agent_type)
        research_prompt = (
            f"Research the following topic thoroughly and provide your findings. "
            f"Be specific, detailed, and practical. Use your expertise.\n\n"
            f"Topic: {topic}\n\n"
            f"Provide your research findings as structured, actionable content. "
            f"Include specifics: tools, patterns, best practices, trade-offs, "
            f"and concrete recommendations where relevant."
        )

        try:
            response = self.client.messages.create(
                model=self.worker_model,
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": research_prompt}],
            )
            result = next(
                (b.text for b in response.content if hasattr(b, "text")),
                f"Research on '{topic}' completed but produced no text output."
            )
            print(f"      [{agent_type}] research -> {len(result)} chars")
            return result
        except Exception as e:
            return f"Research on '{topic}' failed: {e}"

    def run(self, subtask: str, agent_type: str, attempt: int = 1, prior_feedback: str = "") -> str:
        """Run a specialist worker on a subtask. Returns the worker's final text."""
        system = load_agent_prompt(agent_type)
        self.emitter.emit("worker.started", {"agent": agent_type, "subtask": subtask, "attempt": attempt})

        user_content = subtask
        if prior_feedback:
            user_content = (
                f"{subtask}\n\n"
                f"[Attempt {attempt}/3 — Previous attempt was rejected]\n"
                f"QA Feedback: {prior_feedback}\n"
                f"Please address the feedback and try again."
            )

        messages = [{"role": "user", "content": user_content}]

        # Merge MCP tools with built-in tools
        tools = list(WORKER_TOOLS)
        if self.mcp_bridge:
            tools.extend(self.mcp_bridge.discover_tools())

        for _ in range(6):
            response = self.client.messages.create(
                model=self.worker_model,
                max_tokens=1024,
                system=system,
                tools=tools,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                result = next(
                    (b.text for b in response.content if hasattr(b, "text")),
                    "(no output)"
                )
                self.emitter.emit("worker.completed", {"agent": agent_type, "chars": len(result)})
                return result

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = self._run_tool(block.name, block.input, agent_type)
                print(f"      [{agent_type}] {block.name} -> {result[:70]}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
            messages.append({"role": "user", "content": tool_results})

        return "Worker hit iteration limit."
