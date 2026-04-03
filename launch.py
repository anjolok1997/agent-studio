"""
Agent Studio — Launch

Interactive launcher for Agent Studio. Pick a template, provide materials,
review the execution plan, and let specialist agents do the work.

Default: Signs in via Claude CLI (no API key needed).
Use --api-key to switch to Anthropic SDK mode (pay-per-token).

Run:
    python3 launch.py                                      # Claude CLI login (default)
    python3 launch.py --api-key                            # Use Anthropic API key instead
    python3 launch.py --supervised                         # Legacy: checkpoints + per-task approval
    python3 launch.py --worker-model sonnet                # Use Sonnet for workers
    python3 launch.py --execute --env staging              # Enable real actions
    python3 launch.py --execute --env prod                 # Production (escalates on all non-SAFE tools)
    python3 launch.py --token-limit 50000                  # Lower spending cap
    python3 launch.py mcp add                              # Add an MCP server (interactive)
    python3 launch.py mcp list                             # Show configured servers
    python3 launch.py mcp remove <name>                    # Remove a server
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from studio import Engine, list_available_agents, PermissionGuard, ExecutionMode, SpendingGuard, AuditLog
from studio.permissions import OversightMode
from studio.planner import Planner
from studio.agent_loader import AgentLoader
from studio.llm import LLM

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


def print_banner(oversight_label: str):
    print(f"\n  {BOLD}Agent Studio{RESET} {DIM}— {oversight_label}{RESET}\n")


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
    """Show available models for user reference (--show-models flag)."""
    print(f"\n{BOLD}Available models:{RESET}")
    for name, info in MODEL_INFO.items():
        model_id = MODELS[name]
        print(f"  {CYAN}{name:8s}{RESET} {info['speed']:8s} | {info['cost']:10s} | Best for: {info['best_for']}")
    print(f"  {DIM}Set with --manager-model and --worker-model{RESET}\n")


def suggest_agents(llm: LLM, goal: str, loader: AgentLoader) -> tuple[list[str], str]:
    """Assess task complexity and suggest the right team.

    Returns (agent_ids, complexity) where complexity is 'simple', 'medium', or 'complex'.
    """
    all_agents = loader.list_agents()

    # Build a compact agent catalog for the prompt
    catalog = []
    for agent_id, info in sorted(all_agents.items()):
        desc = info.description[:80] if info.description else info.name
        catalog.append(f"- {agent_id}: {desc}")
    catalog_text = "\n".join(catalog)

    prompt = f"""Assess this goal's complexity, then pick the right team.

GOAL: {goal}

AVAILABLE AGENTS:
{catalog_text}

STEP 1 — Rate complexity on the first line:
- SIMPLE: single clear task, one specialist enough (organize files, summarize a doc, quick question)
- MEDIUM: needs 2 perspectives or steps (code review, research a topic, write + review)
- COMPLEX: multi-step project, real design decisions (build a system, pipeline, multi-part deliverable)

STEP 2 — Pick agents (one per line after the complexity rating):
- SIMPLE: exactly 1 agent
- MEDIUM: exactly 2 agents
- COMPLEX: 3-4 agents
- Prefer generalists (researcher, analyst, writer) for simple tasks

RESPOND IN THIS EXACT FORMAT:
COMPLEXITY: simple
agent-id-here"""

    response = llm.call(
        "You are a team builder. First assess complexity, then pick agents. Be honest — most tasks are simple.",
        prompt,
        max_tokens=256,
    )

    result_text = response.text.strip()

    # Parse complexity
    complexity = "medium"  # default
    for line in result_text.splitlines():
        line_lower = line.strip().lower()
        if line_lower.startswith("complexity:"):
            value = line_lower.split(":", 1)[1].strip()
            if value in ("simple", "medium", "complex"):
                complexity = value
            break

    # Parse agent IDs
    suggested = []
    for line in result_text.splitlines():
        agent_id = line.strip().lstrip("- ").strip()
        if agent_id in all_agents:
            suggested.append(agent_id)

    # Fallback
    if not suggested:
        suggested = ["researcher"]

    return suggested, complexity


def pick_models_interactive(args) -> tuple:
    """Interactive model selection. Returns (manager_model, worker_model)."""
    # If user specified models via CLI flags, use those directly
    if args.manager_model != "sonnet" or args.worker_model != "haiku":
        return select_models(args)

    # Subscription (CLI): better defaults since there's no per-token cost
    # API key: cheaper defaults to save money
    if args.api_key:
        return MODELS["sonnet"], MODELS["haiku"]    # API: save tokens
    else:
        return MODELS["sonnet"], MODELS["sonnet"]   # CLI: quality matters


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
    """Let the user pick agents from the full library + local agents."""
    loader = AgentLoader()
    by_category = loader.agents_by_category()

    # Build a flat numbered list grouped by category
    numbered = []  # (index, AgentInfo)
    idx = 1

    print(f"\n{BOLD}Available agents ({loader.library_count} library + {loader.local_count} custom):{RESET}\n")

    for cat in loader.list_categories():
        agents_in_cat = by_category.get(cat, [])
        if not agents_in_cat:
            continue

        label = "custom (local)" if cat == "custom" else cat
        print(f"  {MAGENTA}{label} ({len(agents_in_cat)}){RESET}")

        for agent in agents_in_cat:
            numbered.append(agent)
            emoji = f"{agent.emoji} " if agent.emoji else ""
            desc = f" — {agent.description[:60]}" if agent.description else ""
            source_tag = f" {DIM}(local){RESET}" if agent.source == "local" else ""
            print(f"    {CYAN}{idx:3}.{RESET} {emoji}{BOLD}{agent.name}{RESET}{source_tag}{desc}")
            idx += 1
        print()

    print(f"{DIM}Enter agent numbers separated by commas (e.g. 1,3,27){RESET}")
    print(f"{DIM}Or type a category name to select all agents in it (e.g. engineering){RESET}")
    choices = input(f"{BOLD}Your team: {RESET}").strip()

    selected = []
    for part in choices.split(","):
        part = part.strip()
        # Check if it's a category name
        if part in by_category:
            selected.extend(a.id for a in by_category[part])
            continue
        # Otherwise treat as a number
        try:
            num = int(part)
            if 1 <= num <= len(numbered):
                selected.append(numbered[num - 1].id)
        except ValueError:
            pass

    if not selected:
        print("No valid agents selected. Using all local custom agents.")
        selected = [a.id for a in by_category.get("custom", [])]
        if not selected:
            selected = list_available_agents()[:5]

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
        "--api-key", action="store_true",
        help="Use Anthropic API key (pay-per-token) instead of Claude CLI login"
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Enable execute mode (allows real actions with approval)"
    )
    parser.add_argument(
        "--supervised", action="store_true",
        help="Legacy mode: checkpoints after each subtask + per-delegation approval"
    )
    parser.add_argument(
        "--no-plan", action="store_true",
        help="Skip the briefing/planning phase and go straight to execution"
    )
    parser.add_argument(
        "--classic-plan", action="store_true",
        help="Use the classic Haiku planning phase instead of interactive manager briefing"
    )
    # Deprecated flags — map to --supervised with warning
    parser.add_argument(
        "--approve-each", action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--no-checkpoints", action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--token-limit", type=int, default=100_000,
        help="Maximum tokens per run (default: 100,000)"
    )
    parser.add_argument(
        "--use-integrations", action="store_true",
        help="Let workers use your Claude integrations (Notion, Slack, etc.)"
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
    parser.add_argument(
        "command", nargs="?", default=None,
        help="'schedule' for recurring tasks, or a goal in quotes for one-shot mode"
    )
    parser.add_argument(
        "subcommand", nargs="?", default=None,
        help="Schedule action: add, list, remove, run, daemon"
    )
    parser.add_argument(
        "schedule_arg", nargs="?", default=None,
        help="Schedule name (for remove/run)"
    )
    return parser.parse_args()


def _is_one_shot(args) -> bool:
    """Check if the user passed a goal as a positional argument."""
    return (args.command is not None
            and args.command not in ("schedule", "mcp")
            and not args.show_models)


def main():
    args = parse_args()

    if args.show_models:
        print_model_menu()
        sys.exit(0)

    # ─── Schedule subcommand ──────────────────────────────────────────────
    # ─── MCP subcommand ────────────────────────────────────────────────────
    if args.command == "mcp":
        from studio.mcp_cli import cli_mcp_add, cli_mcp_list, cli_mcp_remove
        mcp_config_path = Path(args.mcp_config)

        if args.subcommand == "add":
            allow_custom = args.schedule_arg == "--allow-custom"
            cli_mcp_add(mcp_config_path, allow_custom=allow_custom)
            sys.exit(0)
        elif args.subcommand in ("list", "ls"):
            cli_mcp_list(mcp_config_path)
            sys.exit(0)
        elif args.subcommand == "remove":
            if not args.schedule_arg:
                print(f"  {RED}Usage: studio mcp remove <name>{RESET}")
                sys.exit(1)
            cli_mcp_remove(args.schedule_arg, mcp_config_path)
            sys.exit(0)
        else:
            # No subcommand — show list + hint
            cli_mcp_list(mcp_config_path)
            print(f"  {DIM}Commands: studio mcp add | studio mcp list | studio mcp remove <name>{RESET}\n")
            sys.exit(0)

    if args.command == "schedule":
        from studio.scheduler import (
            cli_add_schedule, cli_list_schedules,
            cli_remove_schedule, cli_run_once, cli_daemon,
        )

        if args.subcommand == "add":
            cli_add_schedule()
            sys.exit(0)
        elif args.subcommand == "list":
            cli_list_schedules()
            sys.exit(0)
        elif args.subcommand == "remove":
            if not args.schedule_arg:
                print(f"  {RED}Usage: python3 launch.py schedule remove <name>{RESET}")
                sys.exit(1)
            cli_remove_schedule(args.schedule_arg)
            sys.exit(0)
        elif args.subcommand in ("run", "daemon"):
            sched_provider = "api" if args.api_key else "cli"
            try:
                sched_llm = LLM(provider=sched_provider)
            except RuntimeError as e:
                print(f"\n  {RED}{e}{RESET}")
                sys.exit(1)

            if args.subcommand == "run":
                cli_run_once(sched_llm, args.schedule_arg)
            else:
                cli_daemon(sched_llm)
            sys.exit(0)
        else:
            print(f"\n{BOLD}Schedule commands:{RESET}")
            print(f"  python3 launch.py schedule add        Create a recurring task")
            print(f"  python3 launch.py schedule list       Show all scheduled tasks")
            print(f"  python3 launch.py schedule remove <n> Remove a schedule by name")
            print(f"  python3 launch.py schedule run        Run all due tasks now")
            print(f"  python3 launch.py schedule run <name> Run a specific task now")
            print(f"  python3 launch.py schedule daemon     Run continuously in background")
            print()
            sys.exit(0)

    # ─── Normal interactive mode ──────────────────────────────────────────

    # Handle deprecated flags
    if args.approve_each:
        print(f"  {YELLOW}--approve-each is deprecated. Use --supervised instead.{RESET}")
        args.supervised = True
    if args.no_checkpoints and not args.supervised:
        print(f"  {YELLOW}--no-checkpoints is deprecated. CEO mode (default) has no checkpoints.{RESET}")

    # Determine provider: CLI (default) vs API key
    provider = "api" if args.api_key else "cli"

    use_cli = provider == "cli"

    try:
        # Team builder uses Haiku — it's just classification (picking agents from a list)
        # No reasoning needed, Haiku is fast and accurate for this
        suggest_llm = LLM(provider=provider, model="claude-haiku-4-5-20251001")
        if use_cli:
            print(f"  {GREEN}Signed in via Claude CLI{RESET}")
        else:
            print(f"  {CYAN}Using API key{RESET}")
    except RuntimeError as e:
        print(f"\n  {RED}{e}{RESET}")
        sys.exit(1)

    # Model defaults — subscription gets better models since there's no per-token cost
    manager_model, worker_model = pick_models_interactive(args)
    oversight_mode = OversightMode.SUPERVISED if args.supervised else OversightMode.CEO

    # Set up safety layers
    mode = ExecutionMode.EXECUTE if args.execute else ExecutionMode.DRY_RUN
    permissions = PermissionGuard(mode=mode, environment=args.env, oversight=oversight_mode)
    use_cli = provider == "cli"
    spending = SpendingGuard(
        max_tokens=args.token_limit,
        subscription_mode=use_cli,
    )
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

    print_banner(permissions.get_oversight_label())

    if mcp_bridge and mcp_bridge.connected_servers:
        print(f"  {GREEN}MCP: Connected to {len(mcp_bridge.connected_servers)} server(s): {', '.join(mcp_bridge.connected_servers)}{RESET}\n")

    # Auto-detect Claude integrations (Notion, Slack, etc.)
    claude_integrations = {}
    has_claude_integrations = False
    if use_cli:
        from studio.integrations import detect_claude_integrations
        claude_integrations = detect_claude_integrations()
        connected_names = [n for n, ok in claude_integrations.items() if ok]
        if connected_names:
            has_claude_integrations = True
            print(f"  {GREEN}Integrations:{RESET} {', '.join(connected_names)}\n")

    # Warn if running in execute mode against production
    if args.execute and args.env == "prod":
        print(f"  {RED}{BOLD}WARNING: Execute mode targeting PRODUCTION.{RESET}")
        confirm = input(f"  {BOLD}Are you sure? [y/N]: {RESET}").strip().lower()
        if confirm not in ("y", "yes"):
            print("Aborted.")
            sys.exit(0)
        print()

    # ─── Goal & Team Selection ─────────────────────────────────────────────

    templates = load_templates()
    loader = AgentLoader()

    # One-shot mode: studio "do this task"
    if _is_one_shot(args):
        user_input = args.command
    else:
        user_input = input(f"  {BOLD}What do you need?{RESET} > ").strip()

    template = None
    task_complexity = "medium"  # default, overridden by suggest_agents

    if user_input.lower() in ("templates", "template", "t"):
        # ── Template flow ──
        print()
        print_menu(templates)

        choice = input(f"{BOLD}Select [1-{len(templates)}]: {RESET}").strip()
        try:
            idx = int(choice)
        except ValueError:
            print("Invalid choice.")
            sys.exit(1)

        if 1 <= idx <= len(templates):
            template = templates[idx - 1]
            print(f"\n{GREEN}Template: {template['name']}{RESET}")
            print(f"{DIM}Default goal: {template['goal'][:100]}...{RESET}\n")

            custom = input(f"{BOLD}Customize the goal?{RESET} (Enter to use default, or type your own)\n> ").strip()
            goal = custom if custom else template["goal"]
            agents = template["agents"]
        else:
            print("Invalid choice.")
            sys.exit(1)

    elif user_input.lower() in ("pick", "agents", "browse"):
        # ── Manual agent picker ──
        goal, agents = pick_custom_agents()

    else:
        # ── Default: just type your goal and go ──
        goal = user_input
        if not goal:
            print("No goal provided.")
            sys.exit(1)

        print(f"\n{DIM}Assembling team...{RESET}")
        agents, task_complexity = suggest_agents(suggest_llm, goal, loader)

        # Show the team briefly (no approval needed — just info)
        agent_names = []
        for agent_id in agents:
            info = loader.get_agent(agent_id)
            name = info.name if info else agent_id
            agent_names.append(name)
        print(f"  {GREEN}Team:{RESET} {', '.join(agent_names)} {DIM}({task_complexity}){RESET}\n")

    # Collect materials if using a template
    materials_text = ""
    if template:
        materials_text = collect_materials(template)
    if materials_text:
        goal = f"{materials_text}\n\n{goal}"

    # ─── Briefing / Planning Phase ──────────────────────────────────────────

    briefing_context = None

    if args.classic_plan and not args.no_plan:
        # Legacy: Haiku planner with Y/n approval
        planner = Planner(llm=suggest_llm)

        print(f"\n{DIM}Planning... (using haiku){RESET}")
        plan = planner.create_plan(goal, agents, worker_model, manager_model)
        spending.track(plan["planning_tokens"], 0)

        approved = planner.display_plan(plan, worker_model, manager_model, args.token_limit)
        if not approved:
            print("\nAborted. No tokens spent beyond planning.")
            sys.exit(0)

    elif not args.no_plan:
        # Default: Interactive manager briefing
        from studio.briefing import Briefing
        from studio.mcp_cli import MCP_CATALOG
        from studio.integrations import format_for_briefing

        connected_mcps = mcp_bridge.connected_servers if mcp_bridge else []
        available_mcps = {k: {"name": v["name"], "description": v["description"]}
                          for k, v in MCP_CATALOG.items()}

        manager_llm = LLM(provider=provider, model=manager_model)
        briefing = Briefing(
            llm=manager_llm, agents=agents, goal=goal,
            complexity=task_complexity,
            connected_mcps=connected_mcps, available_mcps=available_mcps,
            claude_integrations_info=format_for_briefing(claude_integrations) if claude_integrations else None,
        )
        briefing_result = briefing.run()
        spending.track(briefing_result.tokens_used, 0)

        if not briefing_result.approved:
            print("\nAborted during briefing. No execution tokens spent.")
            sys.exit(0)

        briefing_context = briefing_result.context

        # Apply speed override from briefing (/fast, /powerful, etc.)
        if briefing_result.speed_override:
            from studio.briefing import SPEED_PRESETS
            manager_model, worker_model = SPEED_PRESETS[briefing_result.speed_override]

    if oversight_mode == OversightMode.CEO:
        print(f"\n  {GREEN}Agents working autonomously. You'll only be asked for critical actions.{RESET}\n")

    engine = Engine(
        manager_model=manager_model,
        worker_model=worker_model,
        permissions=permissions,
        spending_guard=spending,
        audit=audit,
        oversight_mode=oversight_mode,
        mcp_bridge=mcp_bridge,
        provider=provider,
        mcp_config_path=str(mcp_config_path) if mcp_config_path.exists() else None,
        use_claude_integrations=has_claude_integrations or args.use_integrations,
    )

    print(f"\n{GREEN}Launching Agent Studio...{RESET}")
    print(f"{DIM}Team: {', '.join(agents)}{RESET}\n")

    result = engine.run(goal, allowed_agents=agents, briefing_context=briefing_context)

    # ─── Output ───────────────────────────────────────────────────────────────

    print(f"\n{'='*60}")
    print(f"{BOLD}{GREEN}FINAL SUMMARY{RESET}")
    print(f"{'='*60}")
    print(result["summary"])

    if result["artifacts"]:
        from studio.project_builder import process_artifacts

        # Try to extract project files (FILE: blocks) from artifacts
        output_dir = Path("output")
        created_files, remaining = process_artifacts(result["artifacts"], output_dir / "project")

        # Save any remaining artifacts that weren't project files
        if remaining:
            output_dir.mkdir(exist_ok=True)

            print(f"\n{'='*60}")
            print(f"{BOLD}ARTIFACTS ({len(remaining)} produced){RESET}")
            print(f"{'='*60}")
            for i, a in enumerate(remaining, 1):
                content = a["content"]
                if content.strip().startswith("<!DOCTYPE") or content.strip().startswith("<html"):
                    ext = "html"
                elif content.strip().startswith("{") or content.strip().startswith("["):
                    ext = "json"
                else:
                    ext = "md"

                filename = f"artifact_{i}_{a['agent']}.{ext}"
                filepath = output_dir / filename
                filepath.write_text(content)
                print(f"\n  {GREEN}[{i}]{RESET} {BOLD}{filepath}{RESET} ({len(content):,} chars from {a['agent']})")

            # Auto-open HTML files in the browser
            if ext == "html":
                try:
                    abs_path = filepath.resolve()
                    if platform.system() == "Darwin":
                        subprocess.run(["open", str(abs_path)], check=False)
                    elif platform.system() == "Linux":
                        subprocess.run(["xdg-open", str(abs_path)], check=False)
                    elif platform.system() == "Windows":
                        os.startfile(str(abs_path))
                    print(f"  {DIM}Opened in browser{RESET}")
                except Exception:
                    pass

        print(f"\n  {DIM}All artifacts saved to {output_dir}/{RESET}")

    # ─── Follow-up Loop ──────────────────────────────────────────────────

    previous_result = result["summary"]
    previous_artifacts = result.get("artifacts", [])

    while True:
        print(f"\n{DIM}Type a follow-up task, or press Enter to exit.{RESET}")
        followup = input(f"{BOLD}> {RESET}").strip()

        if not followup:
            break

        # Build follow-up goal with context — summary only, not full artifacts
        artifact_refs = ""
        if previous_artifacts:
            refs = [f"- {a['agent']}: {len(a['content']):,} chars" for a in previous_artifacts]
            artifact_refs = f"\n\nPrevious artifacts produced:\n" + "\n".join(refs)

        followup_goal = (
            f"CONTEXT FROM PREVIOUS TASK:\n{previous_result[:2000]}"
            f"{artifact_refs}\n\n"
            f"NEW TASK: {followup}"
        )

        # Auto-suggest agents for the follow-up
        print(f"\n{DIM}Assembling team...{RESET}")
        followup_agents, _ = suggest_agents(suggest_llm, followup, loader)
        agent_names = []
        for agent_id in followup_agents:
            info = loader.get_agent(agent_id)
            agent_names.append(info.name if info else agent_id)
        print(f"  {GREEN}Team:{RESET} {', '.join(agent_names)}\n")

        # Reset spending for the follow-up
        spending = SpendingGuard(
            max_tokens=args.token_limit,
            subscription_mode=use_cli,
        )
        audit = AuditLog()

        engine = Engine(
            manager_model=manager_model,
            worker_model=worker_model,
            permissions=permissions,
            spending_guard=spending,
            audit=audit,
            oversight_mode=oversight_mode,
            mcp_bridge=mcp_bridge,
            provider=provider,
            mcp_config_path=str(mcp_config_path) if mcp_config_path.exists() else None,
            use_claude_integrations=args.use_integrations,
        )

        result = engine.run(followup_goal, allowed_agents=followup_agents)

        print(f"\n{'='*60}")
        print(f"{BOLD}{GREEN}RESULT{RESET}")
        print(f"{'='*60}")
        print(result["summary"])

        if result["artifacts"]:
            output_dir = Path("output")
            output_dir.mkdir(exist_ok=True)

            print(f"\n{'='*60}")
            print(f"{BOLD}ARTIFACTS ({len(result['artifacts'])} produced){RESET}")
            print(f"{'='*60}")
            for i, a in enumerate(result["artifacts"], 1):
                content = a["content"]
                if content.strip().startswith("<!DOCTYPE") or content.strip().startswith("<html"):
                    ext = "html"
                elif content.strip().startswith("{") or content.strip().startswith("["):
                    ext = "json"
                else:
                    ext = "md"
                filename = f"artifact_{i}_{a['agent']}.{ext}"
                filepath = output_dir / filename
                filepath.write_text(content)
                print(f"\n  {GREEN}[{i}]{RESET} {BOLD}{filepath}{RESET} ({len(content):,} chars from {a['agent']})")

            print(f"\n  {DIM}All artifacts saved to {output_dir}/{RESET}")

        previous_result = result["summary"]
        previous_artifacts = result.get("artifacts", [])

    # Cleanup
    print(f"\n{DIM}Done. Thanks for using Agent Studio.{RESET}\n")
    if mcp_bridge:
        mcp_bridge.disconnect_all()


if __name__ == "__main__":
    main()
