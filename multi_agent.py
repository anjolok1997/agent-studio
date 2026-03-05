"""
Multi-Agent Workflow System

Architecture:
  Manager Agent  ─── breaks down goal, delegates subtasks
       │
       └──► Worker Agent  ─── executes a single focused subtask
       └──► Worker Agent  ─── executes a single focused subtask
       └──► ...

How it works:
1. Manager receives a high-level goal
2. Manager calls `delegate_task(subtask)` for each piece of work
3. Each `delegate_task` call spins up a fresh Worker agent
4. Worker executes the subtask and returns a result string
5. Manager collects all results and writes a final summary

Run:  python3 multi_agent.py
"""

import json
import os
from anthropic import Anthropic

client = Anthropic()


# ─── Worker Agent ──────────────────────────────────────────────────────────────
# A focused agent that handles exactly one subtask.
# It has its own tools relevant to execution work.

WORKER_TOOLS = [
    {
        "name": "research",
        "description": "Look up information or think through a topic in depth.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "What to research or think through"},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "draft_output",
        "description": "Write a draft: plan, checklist, document, or any text artifact.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The drafted text"},
            },
            "required": ["content"],
        },
    },
    {
        "name": "flag_blocker",
        "description": "Signal that this subtask is blocked and explain why.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
            },
            "required": ["reason"],
        },
    },
]

# Simulated tool execution for the worker
# In a real system, `research` might call a web search API, `draft_output`
# might write to a file, etc.
worker_artifacts: list[str] = []

def _run_worker_tool(name: str, inputs: dict) -> str:
    if name == "research":
        return f"Research complete on '{inputs['topic']}': key points gathered and analyzed."
    if name == "draft_output":
        worker_artifacts.append(inputs["content"])
        return f"Draft saved ({len(inputs['content'])} chars)."
    if name == "flag_blocker":
        return f"BLOCKED: {inputs['reason']}"
    return f"Unknown tool: {name}"


def run_worker(subtask: str) -> str:
    """
    Spin up a Worker agent to handle one focused subtask.
    Returns a plain-text result the Manager can read.
    """
    print(f"    [Worker] Starting: {subtask!r}")

    messages = [{"role": "user", "content": subtask}]
    system = """You are a focused worker agent. You receive ONE subtask and must complete it.
Use your tools to research, draft output, or flag blockers. When done, respond with a
concise summary of what you accomplished (1-3 sentences)."""

    for _ in range(6):  # workers get fewer iterations — they're focused
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",  # cheaper/faster for worker agents
            max_tokens=1024,
            system=system,
            tools=WORKER_TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            result = next(
                (b.text for b in response.content if hasattr(b, "text")),
                "(worker produced no text)"
            )
            print(f"    [Worker] Done: {result[:80]}...")
            return result

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = _run_worker_tool(block.name, block.input)
            print(f"      [Worker tool] {block.name} -> {result[:60]}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })
        messages.append({"role": "user", "content": tool_results})

    return "Worker hit iteration limit."


# ─── Manager Agent ─────────────────────────────────────────────────────────────
# Knows one special tool: `delegate_task`, which runs a Worker agent.

MANAGER_TOOLS = [
    {
        "name": "delegate_task",
        "description": (
            "Delegate a focused subtask to a worker agent. "
            "The worker will handle it and return a result. "
            "Call this once per subtask — workers work in sequence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subtask": {
                    "type": "string",
                    "description": "Clear, self-contained description of the subtask",
                },
            },
            "required": ["subtask"],
        },
    },
]


def run_manager(goal: str) -> str:
    """
    Manager agent: breaks goal into subtasks, delegates each to a Worker,
    then synthesizes the results into a final summary.
    """
    print(f"\n{'='*60}")
    print(f"MANAGER GOAL: {goal}")
    print(f"{'='*60}\n")

    messages = [{"role": "user", "content": goal}]
    system = """You are a manager agent. When given a high-level goal:
1. Break it into 2-4 focused subtasks.
2. Use delegate_task to send each subtask to a worker agent.
3. Wait for each result, then delegate the next subtask.
4. After all workers are done, write a final summary of what was accomplished.
Keep subtasks concrete and self-contained."""

    for iteration in range(12):
        response = client.messages.create(
            model="claude-sonnet-4-6",  # smarter model for the manager
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
            print(f"\nMANAGER FINISHED after {iteration + 1} iteration(s).\n")
            return final

        tool_results = []
        for block in response.content:
            if hasattr(block, "text") and block.text:
                print(f"[Manager]: {block.text}")
            if block.type != "tool_use":
                continue

            print(f"\n[Manager] Delegating: {block.input['subtask']!r}")
            # This is the key moment: Manager calls Worker
            worker_result = run_worker(block.input["subtask"])

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": worker_result,
            })

        messages.append({"role": "user", "content": tool_results})

    return "Manager hit iteration limit."


# ─── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: Set ANTHROPIC_API_KEY first.")
        exit(1)

    goal = input("Enter your high-level goal (or press Enter for demo): ").strip()
    if not goal:
        goal = "Create a launch plan for a new mobile app: research the market, define the feature set, and draft a go-to-market strategy."

    summary = run_manager(goal)

    print("\nFINAL SUMMARY FROM MANAGER:")
    print("-" * 40)
    print(summary)

    if worker_artifacts:
        print(f"\n[{len(worker_artifacts)} artifact(s) produced by workers]")
        for i, artifact in enumerate(worker_artifacts, 1):
            print(f"\n--- Artifact {i} ---")
            print(artifact[:300] + ("..." if len(artifact) > 300 else ""))
