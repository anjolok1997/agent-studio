"""
MCP CLI — Interactive setup for MCP servers.

`studio mcp add`    — Pick from curated, version-pinned servers.
`studio mcp list`   — Show configured servers.
`studio mcp remove` — Remove a configured server.

Security: All packages are pinned to audited versions. Custom servers
require the --allow-custom flag to prevent supply chain attacks.
"""

from pathlib import Path

import yaml


# ─── Colors ──────────────────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"

# ─── Curated server catalog ─────────────────────────────────────────────────
# Only verified packages with pinned versions. Every entry here has been
# checked on npm and locked to a specific version to prevent supply chain
# attacks. Do NOT use unpinned packages or unverified publishers.
#
# To update versions: run `npm view <package> version` and update here
# after reviewing the changelog.

MCP_CATALOG = {
    "github": {
        "name": "GitHub",
        "description": "Access repos, PRs, issues, and code",
        "publisher": "@modelcontextprotocol (official)",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github@2025.4.8"],
        "env": {"GITHUB_TOKEN": "GitHub personal access token"},
    },
    "filesystem": {
        "name": "Filesystem",
        "description": "Read and write files on your local system",
        "publisher": "@modelcontextprotocol (official)",
        "command": "npx",
        "args_template": ["-y", "@modelcontextprotocol/server-filesystem@2026.1.14", "{path}"],
        "prompts": {"path": "Directory to allow access to (e.g. /Users/you/projects)"},
    },
    "postgres": {
        "name": "PostgreSQL",
        "description": "Query and inspect your Postgres database",
        "publisher": "@modelcontextprotocol (official)",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres@0.6.2"],
        "env": {"DATABASE_URL": "Postgres connection string (postgresql://user:pass@host:5432/db)"},
    },
    "slack": {
        "name": "Slack",
        "description": "Read channels, send messages, search conversations",
        "publisher": "@modelcontextprotocol (official)",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack@2025.4.25"],
        "env": {"SLACK_BOT_TOKEN": "Slack bot token (xoxb-...)"},
    },
    "puppeteer": {
        "name": "Browser / Puppeteer",
        "description": "Browse web pages, fill forms, extract data",
        "publisher": "@modelcontextprotocol (official)",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-puppeteer@2025.5.12"],
        "env": {},
    },
    "redis": {
        "name": "Redis",
        "description": "Inspect keys and data in Redis",
        "publisher": "@modelcontextprotocol (official)",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-redis@2025.4.25"],
        "env": {"REDIS_URL": "Redis connection string (redis://localhost:6379)"},
    },
}

DEFAULT_CONFIG_PATH = Path("mcp_config.yaml")


def _load_config(path: Path = None) -> dict:
    """Load existing config or return empty structure."""
    path = path or DEFAULT_CONFIG_PATH
    if path.exists():
        return yaml.safe_load(path.read_text()) or {"servers": {}}
    return {"servers": {}}


def _save_config(config: dict, path: Path = None):
    """Write config to YAML."""
    path = path or DEFAULT_CONFIG_PATH
    path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False))


# ─── CLI commands ────────────────────────────────────────────────────────────

def cli_mcp_add(config_path: Path = None, allow_custom: bool = False):
    """Interactive: pick an MCP server, configure it, save."""
    config = _load_config(config_path)
    existing = set(config.get("servers", {}).keys())

    # Security notice
    print(f"\n  {GREEN}All servers are version-pinned and from verified publishers.{RESET}")

    # Show catalog
    print(f"\n  {BOLD}Available MCP Servers{RESET}\n")
    entries = list(MCP_CATALOG.items())
    for i, (key, info) in enumerate(entries, 1):
        status = f" {DIM}(already added){RESET}" if key in existing else ""
        publisher = info.get("publisher", "")
        print(f"  {CYAN}{i:>2}.{RESET} {BOLD}{info['name']}{RESET} — {info['description']}{status}")
        print(f"      {DIM}{publisher}{RESET}")

    if allow_custom:
        print(f"\n  {YELLOW} 0. Custom server (unverified — use at your own risk){RESET}")

    # Pick
    print()
    choice = input(f"  {BOLD}Pick a server [1-{len(entries)}]: {RESET}").strip()

    if choice == "0":
        if not allow_custom:
            print(f"\n  {RED}Custom servers are disabled by default for security.{RESET}")
            print(f"  {DIM}Use 'studio mcp add --allow-custom' to enable.{RESET}\n")
            return
        _add_custom(config, config_path)
        return

    try:
        idx = int(choice) - 1
        if not (0 <= idx < len(entries)):
            raise ValueError
    except ValueError:
        print(f"  {RED}Invalid choice.{RESET}")
        return

    key, info = entries[idx]

    if key in existing:
        overwrite = input(f"  {YELLOW}'{key}' already configured. Overwrite? [y/N]: {RESET}").strip().lower()
        if overwrite not in ("y", "yes"):
            print("  Skipped.")
            return

    # Build server config
    server_config = {
        "transport": "stdio",
        "command": info["command"],
    }

    # Handle args with templates (e.g. filesystem needs a path)
    if "args_template" in info:
        prompts = info.get("prompts", {})
        args = []
        for arg in info["args_template"]:
            if arg.startswith("{") and arg.endswith("}"):
                param = arg[1:-1]
                prompt_text = prompts.get(param, param)
                value = input(f"  {BOLD}{prompt_text}: {RESET}").strip()
                if not value:
                    print(f"  {RED}Required. Aborting.{RESET}")
                    return
                args.append(value)
            else:
                args.append(arg)
        server_config["args"] = args
    else:
        server_config["args"] = info.get("args", [])

    # Prompt for env vars
    env_vars = info.get("env", {})
    if env_vars:
        env = {}
        print()
        for var, description in env_vars.items():
            value = input(f"  {BOLD}{description}{RESET}\n  {var}= ").strip()
            if not value:
                print(f"  {RED}Required. Aborting.{RESET}")
                return
            env[var] = value
        server_config["env"] = env

    # Build Docker image if Docker is available
    from .mcp_sandbox import docker_available, ensure_image, DOCKER_CONFIGS

    use_docker = False
    if key in DOCKER_CONFIGS and docker_available():
        print(f"\n  {GREEN}Docker detected — building sandboxed image...{RESET}")
        if ensure_image(key):
            server_config["sandbox"] = "docker"
            use_docker = True
        else:
            print(f"  {YELLOW}Docker build failed. Falling back to direct execution.{RESET}")
    elif key in DOCKER_CONFIGS and not docker_available():
        print(f"\n  {YELLOW}Docker not found. Running without sandbox.{RESET}")
        print(f"  {DIM}Install Docker for supply chain protection: https://docs.docker.com/get-docker/{RESET}")

    # Save
    config.setdefault("servers", {})[key] = server_config
    _save_config(config, config_path)
    print(f"\n  {GREEN}Added '{key}' to {config_path or DEFAULT_CONFIG_PATH}{RESET}")
    if use_docker:
        print(f"  {GREEN}Running in Docker sandbox (network: {DOCKER_CONFIGS[key]['network']}){RESET}")
    print(f"  {DIM}Run 'studio' to start using it.{RESET}\n")


def _add_custom(config: dict, config_path: Path = None):
    """Add a custom MCP server. Only available with --allow-custom."""
    print(f"\n  {YELLOW}{'─' * 56}{RESET}")
    print(f"  {YELLOW}{BOLD}WARNING: Custom servers are unverified.{RESET}")
    print(f"  {YELLOW}You are responsible for auditing the package.{RESET}")
    print(f"  {YELLOW}Pin to an exact version (e.g. @1.2.3) to avoid{RESET}")
    print(f"  {YELLOW}supply chain attacks.{RESET}")
    print(f"  {YELLOW}{'─' * 56}{RESET}")

    confirm = input(f"\n  {BOLD}I understand the risks. Continue? [y/N]: {RESET}").strip().lower()
    if confirm not in ("y", "yes"):
        print("  Aborted.")
        return

    print(f"\n  {BOLD}Custom MCP Server{RESET}\n")

    name = input(f"  {BOLD}Server name (e.g. my-api): {RESET}").strip()
    if not name:
        print(f"  {RED}Name required.{RESET}")
        return

    transport = input(f"  {BOLD}Transport [stdio/sse] (default: stdio): {RESET}").strip() or "stdio"

    server_config = {"transport": transport}

    if transport == "stdio":
        command = input(f"  {BOLD}Command (e.g. npx, python3): {RESET}").strip()
        if not command:
            print(f"  {RED}Command required.{RESET}")
            return
        server_config["command"] = command

        args_str = input(f"  {BOLD}Args (space-separated, PIN YOUR VERSION): {RESET}").strip()
        if args_str:
            server_config["args"] = args_str.split()
    elif transport == "sse":
        url = input(f"  {BOLD}Server URL: {RESET}").strip()
        if not url:
            print(f"  {RED}URL required.{RESET}")
            return
        server_config["url"] = url

    # Optional env vars
    print(f"\n  {DIM}Add environment variables (blank name to finish):{RESET}")
    env = {}
    while True:
        var = input(f"  {BOLD}Env var name: {RESET}").strip()
        if not var:
            break
        val = input(f"  {BOLD}{var}= {RESET}").strip()
        if val:
            env[var] = val
    if env:
        server_config["env"] = env

    config.setdefault("servers", {})[name] = server_config
    _save_config(config, config_path)
    print(f"\n  {GREEN}Added '{name}' to {config_path or DEFAULT_CONFIG_PATH}{RESET}\n")


def cli_mcp_list(config_path: Path = None):
    """Show configured MCP servers."""
    config = _load_config(config_path)
    servers = config.get("servers", {})

    if not servers:
        print(f"\n  {DIM}No MCP servers configured.{RESET}")
        print(f"  {DIM}Run 'studio mcp add' to get started.{RESET}\n")
        return

    print(f"\n  {BOLD}Configured MCP Servers{RESET}\n")
    for name, srv in servers.items():
        transport = srv.get("transport", "stdio")
        if transport == "stdio":
            detail = f"{srv.get('command', '?')} {' '.join(srv.get('args', []))}"
        else:
            detail = srv.get("url", "?")
        env_keys = list(srv.get("env", {}).keys())
        env_str = f" | env: {', '.join(env_keys)}" if env_keys else ""

        # Check if this is a curated server
        curated = name in MCP_CATALOG
        badge = f"{GREEN}verified{RESET}" if curated else f"{YELLOW}custom{RESET}"

        print(f"  {GREEN}●{RESET} {BOLD}{name}{RESET} [{badge}] ({transport})")
        print(f"    {DIM}{detail}{env_str}{RESET}")
    print()


def cli_mcp_remove(name: str, config_path: Path = None):
    """Remove an MCP server from config."""
    config = _load_config(config_path)
    servers = config.get("servers", {})

    if name not in servers:
        print(f"\n  {RED}Server '{name}' not found.{RESET}")
        if servers:
            print(f"  {DIM}Available: {', '.join(servers.keys())}{RESET}")
        return

    del servers[name]
    _save_config(config, config_path)
    print(f"\n  {GREEN}Removed '{name}' from {config_path or DEFAULT_CONFIG_PATH}{RESET}\n")
