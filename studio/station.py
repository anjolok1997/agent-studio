"""
Station — Worker agent execution.

Each worker is a specialist agent that runs a focused subtask
using tools (research, draft_output, flag_blocker).
"""

from pathlib import Path
from anthropic import Anthropic

from .events import EventEmitter

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"

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


def load_agent_prompt(agent_type: str) -> str:
    """Load a specialist system prompt from agents/<agent_type>.md"""
    path = AGENTS_DIR / f"{agent_type}.md"
    if not path.exists():
        available = list_available_agents()
        return f"You are a helpful specialist. (Note: agent type '{agent_type}' not found. Available: {available})"
    return path.read_text()


def list_available_agents() -> list[str]:
    """Return agent types available for assignment."""
    return sorted(p.stem for p in AGENTS_DIR.glob("*.md") if p.stem != "reality-checker")


class Station:
    """Runs a specialist worker agent on a single subtask."""

    def __init__(self, client: Anthropic, worker_model: str = "claude-haiku-4-5-20251001", emitter: EventEmitter = None):
        self.client = client
        self.worker_model = worker_model
        self.emitter = emitter or EventEmitter()
        self.artifacts: list[dict] = []

    def _run_tool(self, name: str, inputs: dict, agent_type: str) -> str:
        if name == "research":
            self.emitter.emit("worker.tool_called", {"agent": agent_type, "tool": name, "topic": inputs["topic"]})
            return f"[{agent_type}] Research complete on '{inputs['topic']}'."
        if name == "draft_output":
            self.artifacts.append({"agent": agent_type, "content": inputs["content"]})
            self.emitter.emit("worker.tool_called", {"agent": agent_type, "tool": name, "chars": len(inputs["content"])})
            return f"[{agent_type}] Draft saved ({len(inputs['content'])} chars)."
        if name == "flag_blocker":
            self.emitter.emit("worker.blocked", {"agent": agent_type, "reason": inputs["reason"]})
            return f"[{agent_type}] BLOCKED: {inputs['reason']}"
        return f"Unknown tool: {name}"

    def run(self, subtask: str, agent_type: str, attempt: int = 1, prior_feedback: str = "") -> str:
        """Run a specialist worker on a subtask. Returns the worker's final text."""
        system = load_agent_prompt(agent_type)
        self.emitter.emit("worker.started", {"agent": agent_type, "subtask": subtask, "attempt": attempt})

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
            response = self.client.messages.create(
                model=self.worker_model,
                max_tokens=1024,
                system=system,
                tools=WORKER_TOOLS,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                result = next(
                    (b.text for b in response.content if hasattr(b, "text")),
                    "(no output)"
                )
                self.emitter.emit("worker.completed", {"agent": agent_type, "chars": len(result)})
                return result

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = self._run_tool(block.name, block.input, agent_type)
                print(f"      [{agent_type}] {block.name} -> {result[:70]}")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
            messages.append({"role": "user", "content": tool_results})

        return "Worker hit iteration limit."
