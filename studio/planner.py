"""
Planner — Lightweight planning phase before execution.

Uses a cheap model (Haiku) to break the goal into subtasks,
estimate cost/time, and detect infrastructure keywords.
The user reviews the full plan before any expensive execution begins.
"""

import re
from anthropic import Anthropic

from .events import EventEmitter

# ─── ANSI Colors ──────────────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"

# ─── Cost and Time Estimates ─────────────────────────────────────────────────

# Approximate tokens per subtask (worker call + QA check)
TOKENS_PER_SUBTASK = {
    "claude-haiku-4-5-20251001": 8_000,
    "claude-sonnet-4-6": 15_000,
    "claude-opus-4-6": 30_000,
}

# Approximate seconds per subtask
SECONDS_PER_SUBTASK = {
    "claude-haiku-4-5-20251001": 40,
    "claude-sonnet-4-6": 70,
    "claude-opus-4-6": 120,
}

# Cost per 1M tokens (input + output blended estimate)
COST_PER_MILLION = {
    "claude-haiku-4-5-20251001": 1.00,
    "claude-sonnet-4-6": 9.00,
    "claude-opus-4-6": 30.00,
}

# Infrastructure keywords to detect
INFRA_KEYWORDS = {
    "AWS": ["aws", "s3", "ec2", "lambda", "rds", "ecs", "eks", "msk", "redshift", "sagemaker", "cloudwatch", "iam"],
    "GCP": ["gcp", "bigquery", "cloud run", "gke", "pubsub", "dataflow", "cloud storage", "vertex"],
    "Azure": ["azure", "cosmos", "aks", "blob storage", "synapse", "event hub"],
    "Databases": ["postgres", "mysql", "mongodb", "redis", "elasticsearch", "dynamodb", "snowflake"],
    "Streaming": ["kafka", "flink", "spark streaming", "kinesis", "pulsar"],
    "Orchestration": ["airflow", "dagster", "prefect", "step functions"],
    "Containers": ["docker", "kubernetes", "k8s", "helm"],
    "CI/CD": ["github actions", "jenkins", "terraform", "pulumi", "cloudformation"],
    "Monitoring": ["datadog", "grafana", "prometheus", "pagerduty", "opsgenie"],
}


def _detect_infra(text: str) -> list[str]:
    """Detect infrastructure keywords in the goal text. Zero API calls."""
    text_lower = text.lower()
    found = []
    for category, keywords in INFRA_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            matches = [kw for kw in keywords if kw in text_lower]
            found.append(f"{category} ({', '.join(matches)})")
    return found


def _estimate_tokens(num_subtasks: int, worker_model: str, manager_model: str) -> int:
    """Estimate total tokens for the run."""
    manager_tokens = TOKENS_PER_SUBTASK.get(manager_model, 15_000)
    worker_tokens = TOKENS_PER_SUBTASK.get(worker_model, 8_000)
    return manager_tokens + (num_subtasks * worker_tokens)


def _estimate_time(num_subtasks: int, worker_model: str) -> str:
    """Estimate run time as a human-readable range."""
    secs = SECONDS_PER_SUBTASK.get(worker_model, 60)
    low = num_subtasks * secs
    high = int(low * 1.5)  # Account for QA retries
    if low < 60:
        return f"~{low}-{high} seconds"
    return f"~{low // 60}-{high // 60} minutes"


def _estimate_cost(tokens: int, worker_model: str) -> str:
    """Estimate cost in dollars."""
    rate = COST_PER_MILLION.get(worker_model, 1.00)
    cost = (tokens / 1_000_000) * rate
    if cost < 0.01:
        return f"<$0.01"
    return f"~${cost:.2f}"


class Planner:
    """
    Generates a lightweight execution plan before running the full engine.
    Uses Haiku for the planning call to minimize cost.
    """

    def __init__(self, client: Anthropic, planner_model: str = "claude-haiku-4-5-20251001",
                 emitter: EventEmitter = None):
        self.client = client
        self.planner_model = planner_model
        self.emitter = emitter or EventEmitter()

    def create_plan(self, goal: str, allowed_agents: list[str],
                    worker_model: str, manager_model: str) -> dict:
        """
        Generate an execution plan. Returns a dict with:
        - subtasks: list of {agent_type, description}
        - token_estimate, cost_estimate, time_estimate
        - infrastructure: detected infra keywords
        - planning_tokens: tokens used for this planning call
        """
        self.emitter.emit("planner.started", {"goal": goal[:80]})

        response = self.client.messages.create(
            model=self.planner_model,
            max_tokens=512,
            system=(
                "You are a project planner. Given a goal and available specialists, "
                "break it into 2-4 focused subtasks. For each subtask, assign the best specialist.\n\n"
                "Respond in EXACTLY this format, one subtask per line:\n"
                "SUBTASK: [agent-type] Description of the subtask\n\n"
                "Nothing else. No numbering, no extra text."
            ),
            messages=[{
                "role": "user",
                "content": (
                    f"Goal: {goal}\n\n"
                    f"Available specialists: {', '.join(allowed_agents)}\n\n"
                    f"Break this into 2-4 subtasks."
                )
            }],
        )

        plan_text = response.content[0].text.strip()
        planning_tokens = 0
        if hasattr(response, "usage"):
            planning_tokens = response.usage.input_tokens + response.usage.output_tokens

        # Parse subtasks
        subtasks = []
        for line in plan_text.split("\n"):
            line = line.strip()
            if not line.upper().startswith("SUBTASK:"):
                continue
            rest = line[len("SUBTASK:"):].strip()
            # Extract [agent-type]
            match = re.match(r"\[([^\]]+)\]\s*(.*)", rest)
            if match:
                agent_type = match.group(1).strip()
                description = match.group(2).strip()
                if agent_type in allowed_agents:
                    subtasks.append({"agent_type": agent_type, "description": description})

        if not subtasks:
            # Fallback: couldn't parse structured output, estimate 3 subtasks
            subtasks = [{"agent_type": allowed_agents[0], "description": "(plan could not be parsed — will use default planning)"}]

        num_subtasks = len(subtasks)
        token_est = _estimate_tokens(num_subtasks, worker_model, manager_model)
        infra = _detect_infra(goal)

        self.emitter.emit("planner.completed", {"subtasks": num_subtasks})

        return {
            "subtasks": subtasks,
            "num_subtasks": num_subtasks,
            "token_estimate": token_est,
            "cost_estimate": _estimate_cost(token_est, worker_model),
            "time_estimate": _estimate_time(num_subtasks, worker_model),
            "infrastructure": infra,
            "planning_tokens": planning_tokens,
            "raw_plan": plan_text,
        }

    def display_plan(self, plan: dict, worker_model: str, manager_model: str, token_limit: int) -> bool:
        """
        Display the plan and ask user to proceed.
        Returns True if user approves, False if rejected.
        """
        print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
        print(f"{BOLD}{CYAN}  EXECUTION PLAN{RESET}")
        print(f"{CYAN}{'='*60}{RESET}")

        print(f"\n{BOLD}  Subtasks:{RESET}")
        for i, st in enumerate(plan["subtasks"], 1):
            print(f"    {CYAN}{i}.{RESET} [{BOLD}{st['agent_type']}{RESET}] {st['description']}")

        print(f"\n{BOLD}  Estimates:{RESET}")
        print(f"    AI cost:       {GREEN}{plan['cost_estimate']}{RESET}")
        print(f"    Tokens:        ~{plan['token_estimate']:,} / {token_limit:,} limit")
        print(f"    Time:          {plan['time_estimate']}")
        print(f"    Models:        Manager={manager_model}, Workers={worker_model}")

        if plan["infrastructure"]:
            print(f"\n{BOLD}  Infrastructure detected:{RESET}")
            for infra in plan["infrastructure"]:
                print(f"    {YELLOW}•{RESET} {infra}")
            print(f"    {DIM}Tip: check pricing at your cloud provider before implementing{RESET}")

        if plan["token_estimate"] > token_limit:
            print(f"\n  {RED}{BOLD}WARNING: Estimated tokens ({plan['token_estimate']:,}) exceed your limit ({token_limit:,}).{RESET}")
            print(f"  {DIM}The run may be cut short. Consider raising --token-limit.{RESET}")

        print(f"\n{CYAN}{'='*60}{RESET}")

        response = input(f"  {BOLD}Proceed? [Y/n]: {RESET}").strip().lower()
        return response not in ("n", "no")
