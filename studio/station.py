"""
Station — Worker agent execution.

Each worker is a specialist agent that runs a focused subtask.
Uses LLM.call() — no SDK-specific interfaces.
"""

from .llm import LLM
from .events import EventEmitter
from .permissions import PermissionGuard
from .agent_loader import AgentLoader


# Shared loader instance
_default_loader: AgentLoader = None


def _get_loader() -> AgentLoader:
    global _default_loader
    if _default_loader is None:
        _default_loader = AgentLoader()
    return _default_loader


def load_agent_prompt(agent_type: str) -> str:
    """Load a specialist system prompt by agent ID."""
    return _get_loader().load_prompt(agent_type)


def list_available_agents() -> list[str]:
    """Return all available agent IDs (library + local)."""
    return _get_loader().list_agent_ids()


def get_agent_loader() -> AgentLoader:
    """Get the shared AgentLoader instance."""
    return _get_loader()


class Station:
    """Runs a specialist worker agent on a single subtask."""

    def __init__(self, llm: LLM = None, emitter: EventEmitter = None,
                 permissions: PermissionGuard = None, mcp_bridge=None):
        self.llm = llm or LLM()
        self.emitter = emitter or EventEmitter()
        self.permissions = permissions or PermissionGuard()
        self.mcp_bridge = mcp_bridge
        self.artifacts: list[dict] = []

    def _do_research(self, topic: str, agent_type: str) -> str:
        """Actually research a topic using the model's knowledge."""
        system = load_agent_prompt(agent_type)
        prompt = (
            f"Research the following topic thoroughly and provide your findings. "
            f"Be specific, detailed, and practical. Use your expertise.\n\n"
            f"Topic: {topic}\n\n"
            f"Provide structured, actionable content. Include specifics: "
            f"tools, patterns, best practices, trade-offs, and concrete "
            f"recommendations where relevant."
        )

        response = self.llm.call(system, prompt, max_tokens=2048)
        print(f"      [{agent_type}] research -> {len(response.text)} chars")
        return response.text

    def run(self, subtask: str, agent_type: str, attempt: int = 1, prior_feedback: str = "") -> str:
        """Run a specialist worker on a subtask. Returns the worker's final text."""
        system = load_agent_prompt(agent_type)
        self.emitter.emit("worker.started", {"agent": agent_type, "subtask": subtask, "attempt": attempt})

        prompt = subtask
        if prior_feedback:
            prompt = (
                f"{subtask}\n\n"
                f"[Attempt {attempt}/{2} — Previous attempt was rejected]\n"
                f"QA Feedback: {prior_feedback}\n"
                f"Please address the feedback and try again."
            )

        prompt += (
            "\n\nIMPORTANT: Produce your complete deliverable directly. "
            "Be thorough and specific. Do not ask for clarification — "
            "use your expertise to make reasonable decisions."
        )

        response = self.llm.call(system, prompt, max_tokens=4096)
        result = response.text

        # If the result looks like it needs research, do it
        if len(result) < 200 and ("research" in result.lower() or "investigate" in result.lower()):
            research = self._do_research(subtask, agent_type)
            # Re-run with research context
            prompt_with_research = (
                f"{prompt}\n\n"
                f"RESEARCH FINDINGS:\n{research[:3000]}\n\n"
                f"Now produce your final deliverable based on these findings."
            )
            response = self.llm.call(system, prompt_with_research, max_tokens=4096)
            result = response.text

        # Check for draft artifacts in the output
        if len(result) > 500:
            self.artifacts.append({"agent": agent_type, "content": result})
            self.emitter.emit("worker.tool_called", {
                "agent": agent_type, "tool": "draft_output", "chars": len(result),
            })

        self.emitter.emit("worker.completed", {"agent": agent_type, "chars": len(result)})
        return result
