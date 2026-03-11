"""
Agent Studio — Launch

Interactive launcher for Agent Studio. Pick a template, customize your goal,
and let specialist agents do the work.

Run:
    python3 launch.py
"""

import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from studio import Engine, list_available_agents

load_dotenv()

TEMPLATES_DIR = Path(__file__).parent / "templates"

# ─── ANSI Colors ──────────────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RESET = "\033[0m"


def load_templates() -> list[dict]:
    """Load all YAML templates, sorted by name."""
    templates = []
    for path in sorted(TEMPLATES_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        data["_path"] = path
        templates.append(data)
    return templates


def print_banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════╗
║               AGENT STUDIO                           ║
║     Assemble your team. Pick a project. Launch.      ║
╚══════════════════════════════════════════════════════╝{RESET}
""")


def print_menu(templates: list[dict]):
    print(f"{BOLD}Select a project template:{RESET}\n")
    for i, t in enumerate(templates, 1):
        agents_str = ", ".join(t["agents"])
        print(f"  {BOLD}{CYAN}{i}.{RESET} {BOLD}{t['name']}{RESET}")
        print(f"     {DIM}{t['description']}{RESET}")
        print(f"     {MAGENTA}Team: {agents_str}{RESET}")
        print()

    print(f"  {BOLD}{CYAN}0.{RESET} {BOLD}Custom project{RESET}")
    print(f"     {DIM}Write your own goal and pick agents{RESET}")
    print()


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


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(f"\n{YELLOW}Set your API key first:{RESET}")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        print(f"  {DIM}or add it to a .env file in this directory{RESET}\n")
        sys.exit(1)

    print_banner()

    templates = load_templates()
    if not templates:
        print("No templates found in templates/ directory.")
        sys.exit(1)

    print_menu(templates)

    choice = input(f"{BOLD}Select [0-{len(templates)}]: {RESET}").strip()
    try:
        idx = int(choice)
    except ValueError:
        print("Invalid choice.")
        sys.exit(1)

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

    print(f"\n{GREEN}Launching Agent Studio...{RESET}")
    print(f"{DIM}Team: {', '.join(agents)}{RESET}\n")

    engine = Engine()
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


if __name__ == "__main__":
    main()
