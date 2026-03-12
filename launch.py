"""
Agent Studio — Launch

Interactive launcher for Agent Studio. Pick a template, provide materials,
review the execution plan, and let specialist agents do the work.

Run:
    python3 launch.py
    python3 launch.py --worker-model claude-sonnet-4-6    # Use Sonnet for workers
    python3 launch.py --execute --env staging              # Enable real actions
    python3 launch.py --approve-each                       # Approve every subtask individually
    python3 launch.py --token-limit 50000                  # Lower spending cap
    python3 launch.py --mcp-config mcp.yaml                # Connect to MCP servers
"""

import argparse
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from studio import Engine, list_available_agents, PermissionGuard, ExecutionMode, SpendingGuard, AuditLog
from studio.planner import Planner

load_dotenv()

TEMPLATES_DIR = Path(__file__).parent / "templates"

# ─── ANSI Colors ──────────────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RED = "\033[31m"
RESET = "\033[0m"

# ─── Available Models ─────────────────────────────────────────────────────────

MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6",
}

MODEL_INFO = {
    "haiku":  {"speed": "fastest", "cost": "cheapest",  "best_for": "simple tasks, summaries"},
    "sonnet": {"speed": "fast",    "cost": "moderate",  "best_for": "complex reasoning, planning"},
    "opus":   {"speed": "slower",  "cost": "expensive", "best_for": "deep analysis, nuanced tasks"},
}


def load_templates() -> list[dict]:
    """Load all YAML templates, sorted by name."""
    templates = []
    for path in sorted(TEMPLATES_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        data["_path"] = path
        templates.append(data)
    return templates


def print_banner(mode_label: str):
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════╗
║               AGENT STUDIO                           ║
║     Assemble your team. Pick a project. Launch.      ║
╚══════════════════════════════════════════════════════╝{RESET}
  Mode: {mode_label}
""")


def print_menu(templates: list[dict]):
    print(f"{BOLD}Select a project template:{RESET}\n")
    for i, t in enumerate(templates, 1):
        agents_str = ", ".join(t["agents"])
        materials_count = len(t.get("materials", []))
        materials_hint = f" | {materials_count} inputs suggested" if materials_count else ""

        print(f"  {BOLD}{CYAN}{i}.{RESET} {BOLD}{t['name']}{RESET}")
        print(f"     {DIM}{t['description']}{RESET}")
        print(f"     {MAGENTA}Team: {agents_str}{materials_hint}{RESET}")
        print()

    print(f"  {BOLD}{CYAN}0.{RESET} {BOLD}Custom project{RESET}")
    print(f"     {DIM}Write your own goal and pick agents{RESET}")
    print()


# ─── Model Selection ─────────────────────────────────────────────────────────

def select_models(args) -> tuple:
    """Resolve manager and worker model IDs from args."""
    manager_model = MODELS.get(args.manager_model, args.manager_model)
    worker_model = MODELS.get(args.worker_model, args.worker_model)
    return manager_model, worker_model


def print_model_menu():
    """Show available models for user reference."""
    print(f"\n{BOLD}Available models:{RESET}")
    for name, info in MODEL_INFO.items():
        model_id = MODELS[name]
        print(f"  {CYAN}{name:8s}{RESET} {info['speed']:8s} | {info['cost']:10s} | Best for: {info['best_for']}")
    print(f"  {DIM}Set with --manager-model and --worker-model{RESET}\n")


# ─── Material Collection ─────────────────────────────────────────────────────

def collect_materials(template: dict) -> str:
    """Prompt user for materials defined in the template."""
    materials_spec = template.get("materials")
    if not materials_spec:
        return ""

    print(f"\n{BOLD}Provide materials for better results:{RESET}")
    print(f"{DIM}(Press Enter to skip optional fields){RESET}\n")

    collected = []

    for mat in materials_spec:
        label = mat["label"]
        hint = mat.get("hint", "")
        mat_type = mat.get("type", "text")
        required = mat.get("required", False)

        req_tag = f" {RED}(required){RESET}" if required else ""
        print(f"  {CYAN}{label}{RESET}{req_tag}")
        if hint:
            print(f"  {DIM}{hint}{RESET}")

        while True:
            if mat_type == "file":
                value = input(f"  {BOLD}File path: {RESET}").strip()
                if value:
                    file_path = Path(value).expanduser()
                    if file_path.exists():
                        try:
                            content = file_path.read_text()
                            collected.append(f"[{label}] (from {file_path.name}):\n{content}")
                            print(f"  {GREEN}Loaded {len(content)} chars from {file_path.name}{RESET}")
                        except Exception as e:
                            print(f"  {RED}Could not read file: {e}{RESET}")
                            if required:
                                continue
                    else:
                        print(f"  {RED}File not found: {value}{RESET}")
                        if required:
                            continue
                elif required:
                    print(f"  {RED}This field is required.{RESET}")
                    continue
            else:
                value = input(f"  {BOLD}> {RESET}").strip()
                if value:
                    collected.append(f"[{label}]: {value}")
                elif required:
                    print(f"  {RED}This field is required.{RESET}")
                    continue

            print()
            break

    if not collected:
        return ""

    materials_text = "=== PROVIDED MATERIALS ===\n"
    materials_text += "\n\n".join(collected)
    materials_text += "\n=== END MATERIALS ==="

    return materials_text


def pick_custom_agents() -> tuple:
    """Let the user pick agents and write a custom goal."""
    available = list_available_agents()
    print(f"\n{BOLD}Available agents:{RESET}\n")
    for i, agent in enumerate(available, 1):
        print(f"  {CYAN}{i}.{RESET} {agent}")

    print(f"\n{DIM}Enter agent numbers separated by commas (e.g. 1,3,5){RESET}")
    choices = input(f"{BOLD}Your team: {RESET}").strip()

    selected = []
    for c in choices.split(","):
        try:
            idx = int(c.strip())
            if 1 <= idx <= len(available):
                selected.append(available[idx - 1])
        except ValueError:
            pass

    if not selected:
        print("No valid agents selected. Using all available.")
        selected = available

    goal = input(f"\n{BOLD}Describe your goal:{RESET}\n> ").strip()
    return goal, selected


def parse_args():
    parser = argparse.ArgumentParser(description="Agent Studio — Interactive Launcher")
    parser.add_argument(
        "--manager-model", type=str, default="sonnet",
        help="Model for the manager agent: haiku, sonnet, opus (default: sonnet)"
    )
    parser.add_argument(
        "--worker-model", type=str, default="haiku",
        help="Model for worker agents: haiku, sonnet, opus (default: haiku)"
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Enable execute mode (allows real actions with approval)"
    )
    parser.add_argument(
        "--approve-each", action="store_true",
        help="Approve each subtask individually instead of the full plan"
    )
    parser.add_argument(
        "--no-plan", action="store_true",
        help="Skip the planning phase and go straight to execution"
    )
    parser.add_argument(
        "--no-checkpoints", action="store_true",
        help="Skip checkpoints after each subtask (run without pausing)"
    )
    parser.add_argument(
        "--token-limit", type=int, default=100_000,
        help="Maximum tokens per run (default: 100,000)"
    )
    parser.add_argument(
        "--env", type=str, default="dev",
        choices=["dev", "staging", "prod"],
        help="Target environment (default: dev)"
    )
    parser.add_argument(
        "--mcp-config", type=str, default="mcp_config.yaml",
        help="Path to MCP server config (default: mcp_config.yaml)"
    )
    parser.add_argument(
        "--show-models", action="store_true",
        help="Show available models and exit"
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.show_models:
        print_model_menu()
        sys.exit(0)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(f"\n{YELLOW}Set your API key first:{RESET}")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        print(f"  {DIM}or add it to a .env file in this directory{RESET}\n")
        sys.exit(1)

    # Resolve models
    manager_model, worker_model = select_models(args)

    # Set up safety layers
    mode = ExecutionMode.EXECUTE if args.execute else ExecutionMode.DRY_RUN
    permissions = PermissionGuard(mode=mode, environment=args.env)
    spending = SpendingGuard(max_tokens=args.token_limit)
    audit = AuditLog()

    # Set up MCP bridge (optional)
    mcp_bridge = None
    mcp_config_path = Path(args.mcp_config)
    if mcp_config_path.exists():
        try:
            from studio.mcp_bridge import MCPBridge
            mcp_bridge = MCPBridge(mcp_config_path, permissions)
            mcp_bridge.connect_all()
        except ImportError:
            print(f"  {DIM}MCP config found but 'mcp' package not installed. Running without MCP.{RESET}")
        except Exception as e:
            print(f"  {YELLOW}MCP setup failed: {e}. Running without MCP.{RESET}")

    print_banner(permissions.get_mode_label())

    if mcp_bridge and mcp_bridge.connected_servers:
        print(f"  {GREEN}MCP: Connected to {len(mcp_bridge.connected_servers)} server(s): {', '.join(mcp_bridge.connected_servers)}{RESET}\n")

    # Warn if running in execute mode against production
    if args.execute and args.env == "prod":
        print(f"  {RED}{BOLD}WARNING: Execute mode targeting PRODUCTION.{RESET}")
        confirm = input(f"  {BOLD}Are you sure? [y/N]: {RESET}").strip().lower()
        if confirm not in ("y", "yes"):
            print("Aborted.")
            sys.exit(0)
        print()

    templates = load_templates()
    if not templates:
        print("No templates found in templates/ directory.")
        sys.exit(1)

    print(f"  {DIM}Models: Manager={manager_model}, Workers={worker_model}{RESET}\n")
    print_menu(templates)

    choice = input(f"{BOLD}Select [0-{len(templates)}]: {RESET}").strip()
    try:
        idx = int(choice)
    except ValueError:
        print("Invalid choice.")
        sys.exit(1)

    template = None
    if idx == 0:
        goal, agents = pick_custom_agents()
    elif 1 <= idx <= len(templates):
        template = templates[idx - 1]
        print(f"\n{GREEN}Template: {template['name']}{RESET}")
        print(f"{DIM}Default goal: {template['goal'][:100]}...{RESET}\n")

        custom = input(f"{BOLD}Customize the goal?{RESET} (Enter to use default, or type your own)\n> ").strip()
        goal = custom if custom else template["goal"]
        agents = template["agents"]
    else:
        print("Invalid choice.")
        sys.exit(1)

    # Collect materials
    materials_text = ""
    if template:
        materials_text = collect_materials(template)
    if materials_text:
        goal = f"{materials_text}\n\n{goal}"

    # ─── Planning Phase ───────────────────────────────────────────────────────

    use_plan_approval = not args.no_plan and not args.approve_each

    if use_plan_approval:
        from anthropic import Anthropic
        client = Anthropic()
        planner = Planner(client)

        print(f"\n{DIM}Planning... (using haiku){RESET}")
        plan = planner.create_plan(goal, agents, worker_model, manager_model)

        # Track planning tokens against spending cap
        spending.track(plan["planning_tokens"], 0)

        approved = planner.display_plan(plan, worker_model, manager_model, args.token_limit)
        if not approved:
            print("\nAborted. No tokens spent beyond planning.")
            sys.exit(0)

        # Use the same client for the engine
        engine = Engine(
            client=client,
            manager_model=manager_model,
            worker_model=worker_model,
            permissions=permissions,
            spending_guard=spending,
            audit=audit,
            human_approval=False,  # Plan was approved — no per-task approval
            checkpoints=not args.no_checkpoints,
            mcp_bridge=mcp_bridge,
        )
    else:
        # --approve-each or --no-plan mode
        human_approval = args.approve_each

        if args.approve_each and not args.no_plan:
            print(f"\n  {YELLOW}Per-task approval enabled. You will approve each delegation individually.{RESET}\n")

        engine = Engine(
            manager_model=manager_model,
            worker_model=worker_model,
            permissions=permissions,
            spending_guard=spending,
            audit=audit,
            human_approval=human_approval,
            checkpoints=not args.no_checkpoints,
            mcp_bridge=mcp_bridge,
        )

    print(f"\n{GREEN}Launching Agent Studio...{RESET}")
    print(f"{DIM}Team: {', '.join(agents)}{RESET}\n")

    result = engine.run(goal, allowed_agents=agents)

    # ─── Output ───────────────────────────────────────────────────────────────

    print(f"\n{'='*60}")
    print(f"{BOLD}{GREEN}FINAL SUMMARY{RESET}")
    print(f"{'='*60}")
    print(result["summary"])

    if result["artifacts"]:
        print(f"\n{'='*60}")
        print(f"{BOLD}ARTIFACTS ({len(result['artifacts'])} produced){RESET}")
        print(f"{'='*60}")
        for i, a in enumerate(result["artifacts"], 1):
            print(f"\n{CYAN}--- [{i}] From {a['agent']} ---{RESET}")
            print(a["content"])

    # Cleanup
    if mcp_bridge:
        mcp_bridge.disconnect_all()


if __name__ == "__main__":
    main()
