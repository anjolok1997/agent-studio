"""
Planner — Lightweight planning phase before execution.

Uses a cheap model (Haiku) to break the goal into subtasks,
estimate cost/time, detect infrastructure keywords, and assess
material size impact on token usage.

The user reviews the full plan before any expensive execution begins.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from .llm import LLM
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

# Approximate tokens per subtask (worker call + QA check), excluding material
TOKENS_PER_SUBTASK = {
    "claude-haiku-4-5-20251001": 8_000,
    "claude-sonnet-4-6": 15_000,
    "claude-opus-4-6": 30_000,
}

# Default seconds per subtask (used when no historical data exists)
# Based on measured runs: ~200s for haiku, higher for smarter models
DEFAULT_SECONDS_PER_SUBTASK = {
    "claude-haiku-4-5-20251001": 200,
    "claude-sonnet-4-6": 300,
    "claude-opus-4-6": 450,
}

# Cost per 1M tokens (input + output blended estimate)
COST_PER_MILLION = {
    "claude-haiku-4-5-20251001": 1.00,
    "claude-sonnet-4-6": 9.00,
    "claude-opus-4-6": 30.00,
}

# Context window limits per model
CONTEXT_LIMITS = {
    "claude-haiku-4-5-20251001": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-6": 200_000,
}

# Approximate chars per token (for estimating material token count)
CHARS_PER_TOKEN = 4

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

# Suggested tools/MCP servers based on task content
TOOL_SUGGESTIONS = {
    # Database connectors
    "postgres": {
        "name": "PostgreSQL",
        "mcp": "@modelcontextprotocol/server-postgres",
        "use": "Query and inspect your Postgres database directly",
    },
    "mysql": {
        "name": "MySQL",
        "mcp": "@modelcontextprotocol/server-mysql",
        "use": "Query and inspect your MySQL database",
    },
    "mongodb": {
        "name": "MongoDB",
        "mcp": "@anthropic-ai/server-mongodb",
        "use": "Query your MongoDB collections",
    },
    "snowflake": {
        "name": "Snowflake",
        "mcp": "@modelcontextprotocol/server-snowflake",
        "use": "Query your Snowflake warehouse",
    },
    "redis": {
        "name": "Redis",
        "mcp": "@modelcontextprotocol/server-redis",
        "use": "Inspect keys and data in Redis",
    },
    # File and code access
    "file": {
        "name": "Filesystem",
        "mcp": "@modelcontextprotocol/server-filesystem",
        "use": "Read and write files on your local system",
        "keywords": ["local file", "local folder", "pdf", "csv", "read file", "write file", "local document"],
    },
    "github": {
        "name": "GitHub",
        "mcp": "@modelcontextprotocol/server-github",
        "use": "Access repos, PRs, issues, and code",
        "keywords": ["github", "repo", "repository", "pull request", "code review"],
    },
    # Web and search
    "web": {
        "name": "Web Search",
        "mcp": "@anthropic-ai/server-web-search",
        "use": "Search the web for current information",
        "keywords": ["search the web", "web search", "competitor", "market research", "latest news"],
    },
    "browser": {
        "name": "Browser / Puppeteer",
        "mcp": "@modelcontextprotocol/server-puppeteer",
        "use": "Browse web pages, fill forms, extract data",
        "keywords": ["browser", "chrome", "web page", "scrape", "form", "website", "screenshot"],
    },
    # Cloud and infra
    "aws": {
        "name": "AWS",
        "mcp": "@aws/server-aws",
        "use": "Manage AWS resources (S3, EC2, Lambda, etc.)",
        "keywords": ["aws", "s3", "ec2", "lambda", "rds"],
    },
    # Communication
    "slack": {
        "name": "Slack",
        "mcp": "@modelcontextprotocol/server-slack",
        "use": "Read channels, send messages, search conversations",
        "keywords": ["slack", "channel", "message", "team", "notify"],
    },
    "email": {
        "name": "Email / Gmail",
        "mcp": "@anthropic-ai/server-gmail",
        "use": "Read and send emails",
        "keywords": ["email", "gmail", "mail", "send", "inbox"],
    },
}


def _suggest_tools(text: str) -> list[dict]:
    """Suggest tools and MCP servers based on the task description."""
    text_lower = text.lower()
    suggestions = []
    seen = set()

    for key, tool in TOOL_SUGGESTIONS.items():
        keywords = tool.get("keywords", [key])
        matched = False
        for kw in keywords:
            # Use word boundary check to avoid partial matches (e.g. "repo" in "report")
            if f" {kw} " in f" {text_lower} " or f" {kw}." in f" {text_lower}." or text_lower.startswith(kw) or text_lower.endswith(kw):
                matched = True
                break
        if matched and tool["name"] not in seen:
            seen.add(tool["name"])
            suggestions.append(tool)

    return suggestions


def _detect_infra(text: str) -> list[str]:
    """Detect infrastructure keywords in the goal text. Zero API calls."""
    text_lower = text.lower()
    found = []
    for category, keywords in INFRA_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            matches = [kw for kw in keywords if kw in text_lower]
            found.append(f"{category} ({', '.join(matches)})")
    return found


def _estimate_material_tokens(goal: str) -> int:
    """Estimate how many tokens the materials in the goal will consume."""
    # Check if there are embedded materials
    if "=== PROVIDED MATERIALS ===" not in goal:
        return 0
    # Extract material section
    start = goal.index("=== PROVIDED MATERIALS ===")
    end = goal.index("=== END MATERIALS ===") + len("=== END MATERIALS ===") if "=== END MATERIALS ===" in goal else len(goal)
    material_text = goal[start:end]
    return len(material_text) // CHARS_PER_TOKEN


def _assess_material_size(material_tokens: int, worker_model: str) -> dict:
    """
    Assess material size and flag potential issues.
    Returns warnings and recommendations.
    """
    context_limit = CONTEXT_LIMITS.get(worker_model, 200_000)
    result = {
        "material_tokens": material_tokens,
        "size_label": "none",
        "warnings": [],
        "recommendations": [],
    }

    if material_tokens == 0:
        return result

    if material_tokens < 5_000:
        result["size_label"] = "small"
    elif material_tokens < 50_000:
        result["size_label"] = "medium"
    elif material_tokens < 150_000:
        result["size_label"] = "large"
        result["warnings"].append(
            f"Large material (~{material_tokens:,} tokens). Each subtask will include this context."
        )
        result["recommendations"].append(
            "Consider summarizing the material first, then running detailed tasks on the summary."
        )
    else:
        result["size_label"] = "very large"
        result["warnings"].append(
            f"Very large material (~{material_tokens:,} tokens). May exceed context window ({context_limit:,} tokens)."
        )
        result["recommendations"].append(
            "Split the document into sections and run separate sessions per section."
        )
        result["recommendations"].append(
            "Or use the Document Summarizer template first to create a digest, then work from that."
        )

    # Check if material alone approaches context limit
    if material_tokens > context_limit * 0.6:
        result["warnings"].append(
            f"Material uses {material_tokens * 100 // context_limit}% of the context window. "
            f"Workers will have limited room for reasoning."
        )

    return result


def _estimate_tokens(num_subtasks: int, worker_model: str, manager_model: str,
                     material_tokens: int = 0) -> int:
    """Estimate total tokens for the run, including material overhead."""
    manager_tokens = TOKENS_PER_SUBTASK.get(manager_model, 15_000)
    worker_tokens = TOKENS_PER_SUBTASK.get(worker_model, 8_000)

    # Material is sent with each worker call + the manager call
    material_overhead = material_tokens * (num_subtasks + 1)

    return manager_tokens + (num_subtasks * worker_tokens) + material_overhead


def _get_historical_avg():
    """Read past audit logs and calculate average seconds per subtask."""
    logs_dir = Path(__file__).resolve().parent.parent / "logs"
    if not logs_dir.exists():
        return None

    measurements = []
    for log_file in logs_dir.glob("run_*.json"):
        try:
            data = json.loads(log_file.read_text())
            start = datetime.fromisoformat(data["started"])
            end = datetime.fromisoformat(data["completed"])
            total_secs = (end - start).total_seconds()

            num_subtasks = sum(1 for e in data["entries"] if e["event"] == "task.delegated")
            if num_subtasks > 0 and total_secs > 10:
                measurements.append(total_secs / num_subtasks)
        except Exception:
            continue

    if not measurements:
        return None

    return sum(measurements) / len(measurements)


def _estimate_time(num_subtasks: int, worker_model: str, material_tokens: int = 0) -> str:
    """Estimate total run time based on historical data or defaults."""
    # Try to use real data from past runs
    historical_avg = _get_historical_avg()
    if historical_avg:
        secs_per_subtask = historical_avg
    else:
        secs_per_subtask = DEFAULT_SECONDS_PER_SUBTASK.get(worker_model, 200)

    # Large materials add processing time
    if material_tokens > 50_000:
        secs_per_subtask = int(secs_per_subtask * 1.3)
    elif material_tokens > 150_000:
        secs_per_subtask = int(secs_per_subtask * 1.8)

    low = int(num_subtasks * secs_per_subtask)
    high = int(low * 1.3)  # Small buffer for variability

    low_min = low // 60
    high_min = high // 60

    source = "based on your past runs" if historical_avg else "estimated"

    if high_min < 1:
        return f"~{low}-{high} seconds ({source})"
    elif low_min == high_min:
        return f"~{low_min} minutes ({source})"
    else:
        return f"~{low_min}-{high_min} minutes ({source})"


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

    def __init__(self, llm: LLM = None, emitter: EventEmitter = None, provider: str = "auto"):
        self.llm = llm or LLM(provider=provider, model="claude-haiku-4-5-20251001")
        self.emitter = emitter or EventEmitter()

    def create_plan(self, goal: str, allowed_agents: list[str],
                    worker_model: str, manager_model: str) -> dict:
        """
        Generate an execution plan. Returns a dict with:
        - subtasks: list of {agent_type, description}
        - token_estimate, cost_estimate, time_estimate
        - infrastructure: detected infra keywords
        - material_assessment: size analysis and warnings
        - planning_tokens: tokens used for this planning call
        """
        self.emitter.emit("planner.started", {"goal": goal[:80]})

        # Assess material size before the API call
        material_tokens = _estimate_material_tokens(goal)
        material_assessment = _assess_material_size(material_tokens, worker_model)

        # Strip materials from the planning prompt to save tokens
        # (planner only needs the goal, not the full document)
        planning_goal = goal
        if "=== PROVIDED MATERIALS ===" in goal:
            # Keep a note about materials but not the full content
            before = goal[:goal.index("=== PROVIDED MATERIALS ===")]
            after = goal[goal.index("=== END MATERIALS ===") + len("=== END MATERIALS ==="):] if "=== END MATERIALS ===" in goal else ""
            material_note = f"[User provided ~{material_tokens:,} tokens of reference material]"
            planning_goal = f"{before}{material_note}{after}"

        system = (
            "You are a project planner. Given a goal and available specialists, "
            "break it into 2-4 focused subtasks. For each subtask, assign the best specialist.\n\n"
            "Respond in EXACTLY this format, one subtask per line:\n"
            "SUBTASK: [agent-type] Description of the subtask\n\n"
            "Nothing else. No numbering, no extra text."
        )
        prompt = (
            f"Goal: {planning_goal}\n\n"
            f"Available specialists: {', '.join(allowed_agents)}\n\n"
            f"Break this into 2-4 subtasks."
        )

        response = self.llm.call(system, prompt, max_tokens=512)
        plan_text = response.text.strip()
        planning_tokens = response.input_tokens + response.output_tokens

        # Parse subtasks — supports multiple formats:
        #   SUBTASK: [agent-type] Description
        #   SUBTASK: agent-type Description  (no brackets)
        #   1. [agent-type] Description
        #   - [agent-type] Description
        subtasks = []
        for line in plan_text.split("\n"):
            line = line.strip()
            if not line:
                continue

            rest = None

            # Standard format: SUBTASK: ...
            if line.upper().startswith("SUBTASK:"):
                rest = line[len("SUBTASK:"):].strip()
            # Numbered format: "1. [agent] ..." or "1) [agent] ..."
            elif re.match(r"^\d+[.)]\s*\[", line):
                rest = re.sub(r"^\d+[.)]\s*", "", line)
            # Numbered without brackets: "1. agent-type Description"
            elif re.match(r"^\d+[.)]\s+\S", line):
                rest = re.sub(r"^\d+[.)]\s*", "", line)
            # Dash format: "- [agent] ..." or "- agent ..."
            elif line.startswith("- ") or line.startswith("* "):
                rest = line[2:].strip()

            if rest is None:
                continue

            agent_type = None
            description = ""

            # Try bracketed format first: [agent-type] description
            match = re.match(r"\[([^\]]+)\]\s*(.*)", rest)
            if match:
                agent_type = match.group(1).strip()
                description = match.group(2).strip()
            else:
                # Try unbracketed: agent-type description
                # Match known agent IDs at the start
                agent_type = None
                for aid in allowed_agents:
                    if rest.lower().startswith(aid):
                        agent_type = aid
                        description = rest[len(aid):].strip()
                        break
                if not agent_type:
                    # Try first word as agent type
                    parts = rest.split(None, 1)
                    if len(parts) == 2:
                        agent_type = parts[0].strip()
                        description = parts[1].strip()
                    else:
                        continue

            # Strip leading punctuation from description
            description = re.sub(r"^[-:—]\s*", "", description)

            # Match agent to allowed list (exact or partial)
            if agent_type in allowed_agents:
                subtasks.append({"agent_type": agent_type, "description": description})
            else:
                # Try partial match (e.g. "frontend-developer" matches "engineering-frontend-developer")
                matched = [a for a in allowed_agents if agent_type in a or a in agent_type]
                if matched:
                    subtasks.append({"agent_type": matched[0], "description": description})

        if not subtasks:
            # Last resort: distribute goal across all agents evenly
            for i, agent in enumerate(allowed_agents[:4]):
                subtasks.append({"agent_type": agent, "description": f"Handle part {i+1} of: {goal[:100]}"})

        num_subtasks = len(subtasks)
        token_est = _estimate_tokens(num_subtasks, worker_model, manager_model, material_tokens)
        infra = _detect_infra(goal)
        tool_suggestions = _suggest_tools(goal)

        self.emitter.emit("planner.completed", {"subtasks": num_subtasks})

        return {
            "subtasks": subtasks,
            "num_subtasks": num_subtasks,
            "token_estimate": token_est,
            "cost_estimate": _estimate_cost(token_est, worker_model),
            "time_estimate": _estimate_time(num_subtasks, worker_model, material_tokens),
            "infrastructure": infra,
            "tool_suggestions": tool_suggestions,
            "material_assessment": material_assessment,
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

        # Material assessment
        mat = plan.get("material_assessment", {})
        if mat.get("material_tokens", 0) > 0:
            size_label = mat["size_label"]
            mat_tokens = mat["material_tokens"]
            color = GREEN if size_label in ("small", "medium") else YELLOW if size_label == "large" else RED
            print(f"\n{BOLD}  Materials:{RESET}")
            print(f"    Size:          {color}{size_label}{RESET} (~{mat_tokens:,} tokens)")

            for warning in mat.get("warnings", []):
                print(f"    {YELLOW}Warning:{RESET} {warning}")

            for rec in mat.get("recommendations", []):
                print(f"    {CYAN}Tip:{RESET} {rec}")

        print(f"\n{BOLD}  Estimates {DIM}(rough, depends on task complexity){RESET}:")
        print(f"    Time:          {plan['time_estimate']}")
        print(f"    Models:        Manager={manager_model}, Workers={worker_model}")

        if plan["infrastructure"]:
            print(f"\n{BOLD}  Infrastructure detected:{RESET}")
            for infra in plan["infrastructure"]:
                print(f"    {YELLOW}•{RESET} {infra}")

        # Tool suggestions
        tool_suggestions = plan.get("tool_suggestions", [])
        if tool_suggestions:
            print(f"\n{BOLD}  Suggested tools:{RESET}")
            print(f"    {DIM}Connect these for better results (optional):{RESET}")
            for tool in tool_suggestions:
                print(f"    {GREEN}•{RESET} {BOLD}{tool['name']}{RESET} — {tool['use']}")
                print(f"      {DIM}npx {tool['mcp']}{RESET}")
            print(f"\n    {DIM}Add to mcp_config.yaml and rerun with --execute to enable.{RESET}")

        # Warnings
        if plan["token_estimate"] > token_limit:
            print(f"\n  {RED}{BOLD}WARNING: Estimated tokens ({plan['token_estimate']:,}) exceed your limit ({token_limit:,}).{RESET}")
            print(f"  {DIM}The run may be cut short. Consider raising --token-limit or reducing material size.{RESET}")

        print(f"\n{CYAN}{'='*60}{RESET}")

        response = input(f"  {BOLD}Proceed? [Y/n]: {RESET}").strip().lower()
        return response not in ("n", "no")
