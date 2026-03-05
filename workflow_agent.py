"""
Workflow Agent - A simple agent that manages tasks using tool calling.

How it works:
1. You give the agent a goal
2. The agent calls tools (Python functions) to manage tasks
3. The agent loops until it decides the job is done

Run:  python3 workflow_agent.py
Docs: https://docs.anthropic.com/en/api/messages
"""

import json
import os
from anthropic import Anthropic

# ─── In-memory task store ─────────────────────────────────────────────────────
# In a real app, this would be a database or file. For learning, a dict is fine.

tasks: dict[str, dict] = {}
_next_id = 1


# ─── Tool implementations (the actual Python functions) ───────────────────────

def create_task(title: str, description: str = "") -> dict:
    """Add a new task to the workflow."""
    global _next_id
    task_id = str(_next_id)
    _next_id += 1
    tasks[task_id] = {
        "id": task_id,
        "title": title,
        "description": description,
        "status": "todo",
        "notes": [],
    }
    return {"ok": True, "task_id": task_id, "task": tasks[task_id]}


def list_tasks() -> dict:
    """Return all tasks and their current status."""
    return {"tasks": list(tasks.values()), "total": len(tasks)}


def update_task_status(task_id: str, status: str) -> dict:
    """Mark a task as 'todo', 'in_progress', or 'done'."""
    if task_id not in tasks:
        return {"ok": False, "error": f"Task {task_id!r} not found"}
    if status not in ("todo", "in_progress", "done"):
        return {"ok": False, "error": "status must be 'todo', 'in_progress', or 'done'"}
    tasks[task_id]["status"] = status
    return {"ok": True, "task": tasks[task_id]}


def add_note(task_id: str, note: str) -> dict:
    """Append a note to an existing task."""
    if task_id not in tasks:
        return {"ok": False, "error": f"Task {task_id!r} not found"}
    tasks[task_id]["notes"].append(note)
    return {"ok": True, "task": tasks[task_id]}


def summarize_progress() -> dict:
    """Count tasks by status and return a progress snapshot."""
    counts = {"todo": 0, "in_progress": 0, "done": 0}
    for t in tasks.values():
        counts[t["status"]] += 1
    return {"summary": counts, "tasks": list(tasks.values())}


# ─── Tool dispatch table ───────────────────────────────────────────────────────
# Maps tool name → function. The agent will call tools by name.

TOOL_FUNCTIONS = {
    "create_task":        create_task,
    "list_tasks":         list_tasks,
    "update_task_status": update_task_status,
    "add_note":           add_note,
    "summarize_progress": summarize_progress,
}


# ─── Tool definitions (JSON schema sent to Claude) ────────────────────────────
# Claude reads these to know what tools exist and what parameters they take.

TOOLS = [
    {
        "name": "create_task",
        "description": "Create a new task in the workflow.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title":       {"type": "string", "description": "Short task title"},
                "description": {"type": "string", "description": "Optional details"},
            },
            "required": ["title"],
        },
    },
    {
        "name": "list_tasks",
        "description": "List all tasks and their current status.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "update_task_status",
        "description": "Change a task's status to 'todo', 'in_progress', or 'done'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "The task ID"},
                "status":  {"type": "string", "enum": ["todo", "in_progress", "done"]},
            },
            "required": ["task_id", "status"],
        },
    },
    {
        "name": "add_note",
        "description": "Add a note or comment to a task.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "note":    {"type": "string"},
            },
            "required": ["task_id", "note"],
        },
    },
    {
        "name": "summarize_progress",
        "description": "Get a progress summary: how many tasks are todo/in_progress/done.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


# ─── The agent loop ────────────────────────────────────────────────────────────

def run_agent(user_request: str, max_iterations: int = 10) -> str:
    """
    Core agent loop.

    1. Send the user's request to Claude with the tool definitions.
    2. Claude responds with either text OR tool_use blocks.
    3. If tool_use: execute the tool, append the result, loop.
    4. If text only (stop_reason == 'end_turn'): we're done.
    """
    client = Anthropic()  # reads ANTHROPIC_API_KEY from env

    messages = [{"role": "user", "content": user_request}]

    system_prompt = """You are a helpful workflow manager. When given a goal or request:
1. Break it into concrete tasks using create_task.
2. Update task statuses as you work through them.
3. Add notes to tasks to capture important context.
4. Always end with summarize_progress so the user can see the full picture.
Be thorough but concise. Use the tools to do real work, not just describe it."""

    print(f"\n{'='*60}")
    print(f"GOAL: {user_request}")
    print(f"{'='*60}\n")

    for iteration in range(max_iterations):
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        # Append assistant's response to the conversation
        messages.append({"role": "assistant", "content": response.content})

        # Check if Claude is done (no more tool calls)
        if response.stop_reason == "end_turn":
            # Extract the final text response
            final_text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "(no text response)"
            )
            print(f"\nAGENT FINISHED after {iteration + 1} iteration(s).\n")
            return final_text

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                # Print any reasoning text Claude shares between tool calls
                if hasattr(block, "text") and block.text:
                    print(f"[Claude]: {block.text}")
                continue

            tool_name = block.name
            tool_input = block.input
            print(f"  -> Tool: {tool_name}({json.dumps(tool_input)})")

            # Call the actual Python function
            fn = TOOL_FUNCTIONS.get(tool_name)
            if fn is None:
                result = {"error": f"Unknown tool: {tool_name}"}
            else:
                result = fn(**tool_input)

            print(f"     Result: {json.dumps(result)}\n")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
            })

        # Send tool results back to Claude
        messages.append({"role": "user", "content": tool_results})

    return "Max iterations reached."


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Make sure the API key is set
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: Set your ANTHROPIC_API_KEY environment variable first.")
        print("  export ANTHROPIC_API_KEY='sk-ant-...'")
        exit(1)

    # Try different goals to experiment!
    goal = input("Enter your workflow goal (or press Enter for a demo): ").strip()
    if not goal:
        goal = "Plan a 3-step process to launch a new feature: write specs, build it, then deploy."

    final_response = run_agent(goal)
    print("\nFINAL RESPONSE FROM AGENT:")
    print("-" * 40)
    print(final_response)
