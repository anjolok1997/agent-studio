"""
Scheduler — Run Agent Studio tasks on a recurring schedule.

Stores scheduled tasks as YAML files in the schedules/ directory.
Each schedule defines a goal, agents (optional — auto-suggested if omitted),
a cron-like interval, and optional MCP config.

Schedules can be managed via CLI:
    python3 launch.py schedule add
    python3 launch.py schedule list
    python3 launch.py schedule remove <name>
    python3 launch.py schedule run
"""

from __future__ import annotations

import time
import yaml
import json
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field

# ─── ANSI Colors ──────────────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEDULES_DIR = PROJECT_ROOT / "schedules"
RUNS_DIR = PROJECT_ROOT / "runs"


@dataclass
class Schedule:
    """A recurring task schedule."""
    name: str
    goal: str
    every: str                          # e.g. "1h", "30m", "daily", "weekly", "monday 9am"
    agents: list[str] = field(default_factory=list)  # empty = auto-suggest
    manager_model: str = "sonnet"
    worker_model: str = "haiku"
    mcp_config: str = ""
    execute: bool = False
    env: str = "dev"
    enabled: bool = True
    last_run: str = ""                  # ISO timestamp of last run
    created: str = ""                   # ISO timestamp of creation


def _parse_interval(every: str) -> int:
    """Parse an interval string to seconds."""
    every = every.strip().lower()

    # Simple intervals
    if every.endswith("m"):
        try:
            return int(every[:-1]) * 60
        except ValueError:
            pass
    if every.endswith("h"):
        try:
            return int(every[:-1]) * 3600
        except ValueError:
            pass

    # Named intervals
    intervals = {
        "hourly": 3600,
        "daily": 86400,
        "weekly": 604800,
        "every hour": 3600,
        "every day": 86400,
        "every week": 604800,
    }
    if every in intervals:
        return intervals[every]

    # Day-based: "monday", "friday 9am", etc.
    days = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}
    for day_name, day_num in days.items():
        if every.startswith(day_name):
            return 604800  # weekly, aligned to day

    # Default: daily
    return 86400


def _should_run(schedule: Schedule) -> bool:
    """Check if a schedule is due to run."""
    if not schedule.enabled:
        return False
    if not schedule.last_run:
        return True

    interval = _parse_interval(schedule.every)
    last = datetime.fromisoformat(schedule.last_run)
    return datetime.now() - last >= timedelta(seconds=interval)


def load_schedules() -> list[Schedule]:
    """Load all schedules from the schedules/ directory."""
    SCHEDULES_DIR.mkdir(exist_ok=True)
    schedules = []
    for path in sorted(SCHEDULES_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
            schedules.append(Schedule(**data))
        except Exception as e:
            print(f"  {YELLOW}Warning: Could not load {path.name}: {e}{RESET}")
    return schedules


def save_schedule(schedule: Schedule):
    """Save a schedule to disk."""
    SCHEDULES_DIR.mkdir(exist_ok=True)
    path = SCHEDULES_DIR / f"{schedule.name}.yaml"
    data = {
        "name": schedule.name,
        "goal": schedule.goal,
        "every": schedule.every,
        "agents": schedule.agents,
        "manager_model": schedule.manager_model,
        "worker_model": schedule.worker_model,
        "mcp_config": schedule.mcp_config,
        "execute": schedule.execute,
        "env": schedule.env,
        "enabled": schedule.enabled,
        "last_run": schedule.last_run,
        "created": schedule.created,
    }
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    return path


def remove_schedule(name: str) -> bool:
    """Remove a schedule by name."""
    path = SCHEDULES_DIR / f"{name}.yaml"
    if path.exists():
        path.unlink()
        return True
    return False


def save_run_result(schedule_name: str, result: dict):
    """Save the output of a scheduled run."""
    RUNS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = RUNS_DIR / f"{schedule_name}_{timestamp}.json"
    run_data = {
        "schedule": schedule_name,
        "timestamp": datetime.now().isoformat(),
        "summary": result.get("summary", ""),
        "artifacts": [
            {"agent": a["agent"], "content_length": len(a["content"])}
            for a in result.get("artifacts", [])
        ],
        "audit_log": result.get("audit_log", ""),
    }
    path.write_text(json.dumps(run_data, indent=2))
    return path


def list_recent_runs(schedule_name: str = None, limit: int = 5) -> list[dict]:
    """List recent run results."""
    RUNS_DIR.mkdir(exist_ok=True)
    runs = []
    pattern = f"{schedule_name}_*.json" if schedule_name else "*.json"
    for path in sorted(RUNS_DIR.glob(pattern), reverse=True)[:limit]:
        try:
            runs.append(json.loads(path.read_text()))
        except Exception:
            pass
    return runs


# ─── CLI Interface ────────────────────────────────────────────────────────────

def cli_add_schedule():
    """Interactive schedule creation."""
    print(f"\n{BOLD}Create a recurring task{RESET}\n")

    name = input(f"  {BOLD}Name{RESET} (short, no spaces): ").strip().replace(" ", "-").lower()
    if not name:
        print("  Cancelled.")
        return

    goal = input(f"  {BOLD}Task{RESET} (what should the agents do?):\n  > ").strip()
    if not goal:
        print("  Cancelled.")
        return

    print(f"\n  {BOLD}How often?{RESET}")
    print(f"  {DIM}Examples: 30m, 1h, daily, weekly, monday{RESET}")
    every = input(f"  > ").strip()
    if not every:
        every = "daily"

    print(f"\n  {BOLD}Agents{RESET} (comma-separated, or Enter to auto-suggest):")
    agents_input = input(f"  > ").strip()
    agents = [a.strip() for a in agents_input.split(",") if a.strip()] if agents_input else []

    schedule = Schedule(
        name=name,
        goal=goal,
        every=every,
        agents=agents,
        created=datetime.now().isoformat(),
    )

    path = save_schedule(schedule)
    interval = _parse_interval(every)
    human_interval = f"{interval // 3600}h" if interval >= 3600 else f"{interval // 60}m"

    print(f"\n  {GREEN}Scheduled:{RESET} {name}")
    print(f"  {DIM}Runs every {human_interval} | Goal: {goal[:60]}...{RESET}")
    print(f"  {DIM}Saved to {path}{RESET}")
    print(f"\n  Run now with: python3 launch.py schedule run")
    print(f"  Or keep it running: python3 launch.py schedule daemon\n")


def cli_list_schedules():
    """List all schedules."""
    schedules = load_schedules()
    if not schedules:
        print(f"\n  {DIM}No schedules yet. Create one with: python3 launch.py schedule add{RESET}\n")
        return

    print(f"\n{BOLD}Scheduled tasks:{RESET}\n")
    for s in schedules:
        status = f"{GREEN}enabled{RESET}" if s.enabled else f"{RED}disabled{RESET}"
        last = s.last_run[:16] if s.last_run else "never"
        print(f"  {CYAN}{s.name}{RESET} [{status}]")
        print(f"    Task:     {s.goal[:80]}")
        print(f"    Every:    {s.every}")
        if s.agents:
            print(f"    Agents:   {', '.join(s.agents)}")
        else:
            print(f"    Agents:   {DIM}(auto-suggest){RESET}")
        print(f"    Last run: {last}")
        print()


def cli_remove_schedule(name: str):
    """Remove a schedule."""
    if remove_schedule(name):
        print(f"\n  {GREEN}Removed:{RESET} {name}\n")
    else:
        print(f"\n  {RED}Not found:{RESET} {name}\n")


def cli_run_once(client, schedule_name: str = None):
    """Run all due schedules (or a specific one) once."""
    from .permissions import PermissionGuard, ExecutionMode, SpendingGuard, OversightMode
    from .audit import AuditLog
    from .engine import Engine
    from .agent_loader import AgentLoader

    schedules = load_schedules()
    if schedule_name:
        schedules = [s for s in schedules if s.name == schedule_name]
        if not schedules:
            print(f"\n  {RED}Schedule not found:{RESET} {schedule_name}\n")
            return

    MODELS = {
        "haiku": "claude-haiku-4-5-20251001",
        "sonnet": "claude-sonnet-4-6",
        "opus": "claude-opus-4-6",
    }

    loader = AgentLoader()
    ran = 0

    for schedule in schedules:
        if not schedule_name and not _should_run(schedule):
            continue

        print(f"\n{'='*60}")
        print(f"{BOLD}Running:{RESET} {schedule.name}")
        print(f"{BOLD}Task:{RESET} {schedule.goal[:100]}")
        print(f"{'='*60}")

        # Resolve agents
        agents = schedule.agents
        if not agents:
            # Auto-suggest agents for the goal
            from launch import suggest_agents
            agents = suggest_agents(client, schedule.goal, loader)
            agent_names = []
            for aid in agents:
                info = loader.get_agent(aid)
                agent_names.append(info.name if info else aid)
            print(f"  {GREEN}Auto-selected team:{RESET} {', '.join(agent_names)}")

        # Set up and run
        manager_model = MODELS.get(schedule.manager_model, schedule.manager_model)
        worker_model = MODELS.get(schedule.worker_model, schedule.worker_model)
        mode = ExecutionMode.EXECUTE if schedule.execute else ExecutionMode.DRY_RUN
        permissions = PermissionGuard(mode=mode, environment=schedule.env, oversight=OversightMode.CEO)
        spending = SpendingGuard()
        audit = AuditLog()

        engine = Engine(
            client=client,
            manager_model=manager_model,
            worker_model=worker_model,
            permissions=permissions,
            spending_guard=spending,
            audit=audit,
            oversight_mode=OversightMode.CEO,
        )

        result = engine.run(schedule.goal, allowed_agents=agents)

        # Save result
        run_path = save_run_result(schedule.name, result)
        print(f"\n  {GREEN}Done.{RESET} Output saved to {run_path}")

        # Update last_run
        schedule.last_run = datetime.now().isoformat()
        save_schedule(schedule)
        ran += 1

    if ran == 0:
        print(f"\n  {DIM}No schedules due. Use 'schedule run <name>' to force-run one.{RESET}\n")
    else:
        print(f"\n  {GREEN}{ran} task(s) completed.{RESET}\n")


def cli_daemon(client):
    """Run the scheduler daemon — checks and runs due tasks continuously."""
    print(f"\n{BOLD}Agent Studio Scheduler{RESET}")
    print(f"{DIM}Checking for due tasks every 60 seconds. Ctrl+C to stop.{RESET}\n")

    try:
        while True:
            schedules = load_schedules()
            due = [s for s in schedules if _should_run(s)]

            if due:
                for s in due:
                    print(f"  {CYAN}[{datetime.now().strftime('%H:%M')}]{RESET} Running: {s.name}")
                    cli_run_once(client, s.name)
            else:
                next_runs = []
                for s in schedules:
                    if s.enabled and s.last_run:
                        interval = _parse_interval(s.every)
                        last = datetime.fromisoformat(s.last_run)
                        next_run = last + timedelta(seconds=interval)
                        next_runs.append((s.name, next_run))
                if next_runs:
                    next_runs.sort(key=lambda x: x[1])
                    name, when = next_runs[0]
                    diff = when - datetime.now()
                    mins = max(0, int(diff.total_seconds() // 60))
                    print(f"  {DIM}[{datetime.now().strftime('%H:%M')}] Next: {name} in ~{mins}m{RESET}", end="\r")

            time.sleep(60)
    except KeyboardInterrupt:
        print(f"\n\n  {GREEN}Scheduler stopped.{RESET}\n")
