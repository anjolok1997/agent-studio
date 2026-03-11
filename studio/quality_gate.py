"""
Quality Gate — Reality Checker validation.

Validates worker output against subtask requirements.
Supports retries when output doesn't pass QA.
"""

from anthropic import Anthropic

from .events import EventEmitter
from .station import Station, load_agent_prompt

MAX_RETRIES = 3


class QualityGate:
    """Validates worker output using the Reality Checker agent."""

    def __init__(self, client: Anthropic, checker_model: str = "claude-haiku-4-5-20251001", emitter: EventEmitter = None):
        self.client = client
        self.checker_model = checker_model
        self.emitter = emitter or EventEmitter()

    def check(self, subtask: str, worker_output: str) -> tuple:
        """Run the Reality Checker. Returns (approved: bool, feedback: str)."""
        self.emitter.emit("qa.check_started", {"subtask": subtask[:80]})

        checker_prompt = load_agent_prompt("reality-checker")
        response = self.client.messages.create(
            model=self.checker_model,
            max_tokens=512,
            system=checker_prompt,
            messages=[{
                "role": "user",
                "content": f"SUBTASK: {subtask}\n\nWORKER OUTPUT:\n{worker_output}\n\nVerdict?"
            }],
        )
        verdict = response.content[0].text.strip()
        approved = verdict.upper().startswith("APPROVED")

        event_type = "qa.approved" if approved else "qa.rejected"
        self.emitter.emit(event_type, {"verdict": verdict[:100]})
        print(f"    [QA] {verdict[:100]}")

        return approved, verdict

    def validate_with_retries(self, subtask: str, agent_type: str, station: Station) -> str:
        """Delegate to a worker, validate, and retry up to MAX_RETRIES times."""
        print(f"\n  [Manager] -> {agent_type}: {subtask!r}")
        feedback = ""

        for attempt in range(1, MAX_RETRIES + 1):
            result = station.run(subtask, agent_type, attempt=attempt, prior_feedback=feedback)
            print(f"    [{agent_type}] Output ({len(result)} chars): {result[:80]}...")

            approved, feedback = self.check(subtask, result)
            if approved:
                print(f"    [QA] APPROVED on attempt {attempt}")
                return result

            print(f"    [QA] Rejected (attempt {attempt}/{MAX_RETRIES}). Retrying...")

        print(f"    [QA] Failed after {MAX_RETRIES} attempts. Passing best effort to manager.")
        return f"[Not fully approved after {MAX_RETRIES} attempts] {result}"
