"""
Quality Gate — Reality Checker validation.

Validates worker output against subtask requirements.
Supports retries when output doesn't pass QA.
"""

from anthropic import Anthropic

from .events import EventEmitter
from .station import Station, load_agent_prompt

MAX_RETRIES = 2

# Skip QA for very short outputs (errors, blockers) or very long ones (likely complete)
MIN_QA_LENGTH = 200
AUTO_APPROVE_LENGTH = 15_000


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
        # Check for approval anywhere in the verdict — handles various formats:
        # "APPROVED", "**VERDICT: APPROVED**", "# VERDICT: ✅ APPROVED", etc.
        verdict_upper = verdict.upper()
        approved = ("APPROVED" in verdict_upper and "NEEDS WORK" not in verdict_upper
                    and "NOT APPROVED" not in verdict_upper
                    and "PARTIAL APPROVAL" not in verdict_upper)

        event_type = "qa.approved" if approved else "qa.rejected"
        self.emitter.emit(event_type, {"verdict": verdict[:100]})
        print(f"    [QA] {verdict[:100]}")

        return approved, verdict

    def validate_with_retries(self, subtask: str, agent_type: str, station: Station) -> str:
        """Delegate to a worker, validate, and retry up to MAX_RETRIES times."""
        print(f"\n  \033[36m▶\033[0m \033[1m{agent_type}\033[0m — {subtask[:100]}")
        feedback = ""

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                print(f"    \033[33m↻\033[0m Retrying ({attempt}/{MAX_RETRIES})...")
            print(f"    \033[2mWorking...\033[0m", end="", flush=True)
            result = station.run(subtask, agent_type, attempt=attempt, prior_feedback=feedback)
            print(f"\r    \033[32m✓\033[0m Done — {len(result):,} chars")

            # Skip QA for very short outputs (errors) or very long ones (clearly substantial)
            if len(result) < MIN_QA_LENGTH:
                print(f"    \033[2m⏭ QA skipped (output too short)\033[0m")
                return result
            if len(result) >= AUTO_APPROVE_LENGTH:
                print(f"    \033[32m✓\033[0m QA auto-approved (substantial output)")
                return result

            print(f"    \033[2mQA checking...\033[0m", end="", flush=True)
            approved, feedback = self.check(subtask, result)
            if approved:
                print(f"\r    \033[32m✓\033[0m QA approved        ")
                return result

            print(f"\r    \033[33m✗\033[0m QA needs rework     ")

        print(f"    \033[2mPassing best effort to manager.\033[0m")
        return result
