"""
Multi-Agent v2 — Incorporating patterns from agency-agents (github.com/msitarzewski/agency-agents)

New vs v1:
  1. Specialist agents  — workers load a named system prompt from agents/*.md
  2. Quality gate       — a Reality Checker validates each worker output (max 3 retries)
  3. Manager picks role — delegate_task includes an agent_type so the right specialist runs

Architecture:
  Manager (Sonnet)
    ├─ delegate_task(subtask, agent_type="ai-engineer") ─► Worker w/ AI Engineer persona
    │     └─► Reality Checker validates ─► APPROVED or retry
    ├─ delegate_task(subtask, agent_type="backend-architect") ─► Worker w/ Backend persona
    │     └─► Reality Checker validates
    └─ final summary

Run:  python3 multi_agent_v2.py
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()
client = Anthropic()

# ─── Agent Registry ────────────────────────────────────────────────────────────
# Loads system prompts from agents/*.md files.
# Add new agents by dropping a .md file in the agents/ directory.

AGENTS_DIR = Path(__file__).parent / "agents"

def load_agent_prompt(agent_type: str) -> str:
    """Load a specialist system prompt from agents/<agent_type>.md"""
    path = AGENTS_DIR / f"{agent_type}.md"
    if not path.exists():
        available = [p.stem for p in AGENTS_DIR.glob("*.md") if p.stem != "reality-checker"]
        return f"You are a helpful specialist. (Note: agent type '{agent_type}' not found. Available: {available})"
    return path.read_text()

def list_available_agents() -> list[str]:
    """Return agent types the manager can choose from."""
    return [p.stem for p in AGENTS_DIR.glob("*.md") if p.stem != "reality-checker"]


# ─── Worker Tools ──────────────────────────────────────────────────────────────

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

artifacts: list[dict] = []  # Collected outputs from all workers

def _run_worker_tool(name: str, inputs: dict, agent_type: str) -> str:
    if name == "research":
        return f"[{agent_type}] Research complete on '{inputs['topic']}'."
    if name == "draft_output":
        artifacts.append({"agent": agent_type, "content": inputs["content"]})
        return f"[{agent_type}] Draft saved ({len(inputs['content'])} chars)."
    if name == "flag_blocker":
        return f"[{agent_type}] BLOCKED: {inputs['reason']}"
    return f"Unknown tool: {name}"


# ─── Quality Gate (Reality Checker) ───────────────────────────────────────────

def quality_gate(subtask: str, worker_output: str) -> tuple[bool, str]:
    """
    Run the Reality Checker on a worker's output.
    Returns (approved: bool, feedback: str).
    """
    checker_prompt = load_agent_prompt("reality-checker")
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=checker_prompt,
        messages=[{
            "role": "user",
            "content": f"SUBTASK: {subtask}\n\nWORKER OUTPUT:\n{worker_output}\n\nVerdict?"
        }],
    )
    verdict = response.content[0].text.strip()
    approved = verdict.upper().startswith("APPROVED")
    print(f"    [QA] {verdict[:100]}")
    return approved, verdict


# ─── Worker Agent ──────────────────────────────────────────────────────────────

def run_worker(subtask: str, agent_type: str, attempt: int = 1, prior_feedback: str = "") -> str:
    """
    Run a specialist worker on a subtask.
    Returns the worker's final text response.
    """
    system = load_agent_prompt(agent_type)

    user_content = subtask
    if prior_feedback:
        user_content = (
            f"{subtask}\n\n"
            f"[Attempt {attempt}/3 — Previous attempt was rejected]\n"
            f"QA Feedback: {prior_feedback}\n"
            f"Please address the feedback and try again."
        )

    messages = [{"role": "user", "content": user_content}]

    for _ in range(6):
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system,
            tools=WORKER_TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            return next(
                (b.text for b in response.content if hasattr(b, "text")),
                "(no output)"
            )

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = _run_worker_tool(block.name, block.input, agent_type)
            print(f"      [{agent_type}] {block.name} -> {result[:70]}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })
        messages.append({"role": "user", "content": tool_results})

    return "Worker hit iteration limit."


# ─── Delegate with Quality Gate + Retry ───────────────────────────────────────

MAX_RETRIES = 3

def delegate_and_validate(subtask: str, agent_type: str) -> str:
    """
    Delegate a subtask to the right specialist, then validate with the Reality Checker.
    Retries up to MAX_RETRIES times if the QA rejects the output.
    """
    print(f"\n  [Manager] -> {agent_type}: {subtask!r}")
    feedback = ""
    for attempt in range(1, MAX_RETRIES + 1):
        result = run_worker(subtask, agent_type, attempt=attempt, prior_feedback=feedback)
        print(f"    [{agent_type}] Output ({len(result)} chars): {result[:80]}...")

        approved, feedback = quality_gate(subtask, result)
        if approved:
            print(f"    [QA] APPROVED on attempt {attempt}")
            return result

        print(f"    [QA] Rejected (attempt {attempt}/{MAX_RETRIES}). Retrying...")

    print(f"    [QA] Failed after {MAX_RETRIES} attempts. Passing best effort to manager.")
    return f"[Not fully approved after {MAX_RETRIES} attempts] {result}"


# ─── Manager Agent ─────────────────────────────────────────────────────────────

available_agents = list_available_agents()

MANAGER_TOOLS = [
    {
        "name": "delegate_task",
        "description": (
            "Delegate a focused subtask to the right specialist agent. "
            "The specialist will complete the work and a QA agent will validate it. "
            f"Available agent types: {available_agents}"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subtask": {
                    "type": "string",
                    "description": "Clear, self-contained description of what the specialist must deliver",
                },
                "agent_type": {
                    "type": "string",
                    "enum": available_agents,
                    "description": "Which specialist to assign this subtask to",
                },
            },
            "required": ["subtask", "agent_type"],
        },
    },
]


def run_manager(goal: str) -> str:
    print(f"\n{'='*60}")
    print(f"GOAL: {goal}")
    print(f"Available specialists: {available_agents}")
    print(f"{'='*60}\n")

    messages = [{"role": "user", "content": goal}]
    system = f"""You are an orchestrating manager agent. When given a goal:
1. Break it into 2-4 focused subtasks.
2. For each subtask, pick the right specialist from: {available_agents}
3. Use delegate_task to assign each subtask — work sequentially, one at a time.
4. After all workers finish, synthesize their results into a final project summary.

Choosing the right specialist matters: ai-engineer for AI/ML tasks, backend-architect
for systems/APIs, project-manager for planning/sequencing. Pick the best fit."""

    for iteration in range(12):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system,
            tools=MANAGER_TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            final = next(
                (b.text for b in response.content if hasattr(b, "text")),
                "(no summary)"
            )
            print(f"\nMANAGER DONE after {iteration + 1} iteration(s).\n")
            return final

        tool_results = []
        for block in response.content:
            if hasattr(block, "text") and block.text:
                print(f"[Manager]: {block.text}")
            if block.type != "tool_use":
                continue

            # Run specialist + quality gate
            result = delegate_and_validate(
                subtask=block.input["subtask"],
                agent_type=block.input["agent_type"],
            )
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

    return "Manager hit iteration limit."


# ─── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: Set ANTHROPIC_API_KEY first.")
        exit(1)

    print("Available specialists:", list_available_agents())
    goal = input("\nEnter your goal (or Enter for demo): ").strip()
    if not goal:
        goal = (
            "Design a simple AI-powered task management API: "
            "define the backend architecture, then plan the AI features "
            "like smart prioritization and natural language task creation."
        )

    summary = run_manager(goal)

    print("\nFINAL SUMMARY:")
    print("=" * 60)
    print(summary)

    if artifacts:
        print(f"\n{'='*60}")
        print(f"ARTIFACTS PRODUCED ({len(artifacts)}):")
        for i, a in enumerate(artifacts, 1):
            print(f"\n[{i}] From {a['agent']}:")
            print(a["content"][:400] + ("..." if len(a["content"]) > 400 else ""))
