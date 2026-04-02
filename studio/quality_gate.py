"""
Quality Gate — User spot-check for worker output.

Instead of an LLM checking another LLM's work (same blind spots),
the user sees a quick summary and decides: approve, retry with
feedback, or edit directly.
"""

from __future__ import annotations

import time

from .events import EventEmitter
from .station import Station

MAX_RETRIES = 2
PREVIEW_CHARS = 600

# ─── Colors ──────────────────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"


def _preview(text: str, max_chars: int = PREVIEW_CHARS) -> str:
    """Return first and last few lines for a quick glance."""
    text = text.strip()
    if len(text) <= max_chars:
        return text

    half = max_chars // 2
    head = text[:half].rstrip()
    tail = text[-half:].lstrip()
    omitted = len(text) - len(head) - len(tail)
    return f"{head}\n\n  {DIM}... ({omitted:,} chars omitted) ...{RESET}\n\n{tail}"


class QualityGate:
    """User spot-check: shows worker output, lets user approve/reject/edit."""

    def __init__(self, emitter: EventEmitter = None, auto_approve: bool = False, **kwargs):
        self.emitter = emitter or EventEmitter()
        self.auto_approve = auto_approve

    def check(self, subtask: str, worker_output: str, agent_type: str) -> tuple[bool, str]:
        """
        Show the user a preview and ask for verdict.
        Returns (approved: bool, feedback: str).
        """
        self.emitter.emit("qa.check_started", {"subtask": subtask[:80]})

        # Auto-approve mode (for non-interactive runs like scheduler)
        if self.auto_approve:
            self.emitter.emit("qa.approved", {"verdict": "auto-approved"})
            return True, ""

        # Show preview
        print(f"\n  {CYAN}{'─' * 56}{RESET}")
        print(f"  {BOLD}Review: {agent_type}{RESET} — {subtask[:80]}")
        print(f"  {CYAN}{'─' * 56}{RESET}")
        print()
        for line in _preview(worker_output).splitlines():
            print(f"    {line}")
        print()
        print(f"  {DIM}{len(worker_output):,} chars total{RESET}")
        print(f"  {CYAN}{'─' * 56}{RESET}")

        print(f"  {BOLD}[Enter]{RESET} approve  {BOLD}[f]{RESET} feedback & retry  {BOLD}[s]{RESET} skip")
        try:
            choice = input(f"  {BOLD}> {RESET}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return True, ""

        if choice in ("f", "feedback", "r", "retry"):
            feedback = input(f"  {BOLD}What should change?{RESET}\n  > ").strip()
            self.emitter.emit("qa.rejected", {"verdict": f"user feedback: {feedback[:100]}"})
            return False, feedback

        if choice in ("s", "skip"):
            self.emitter.emit("qa.rejected", {"verdict": "user skipped"})
            return False, "__skip__"

        # Enter or anything else = approve
        self.emitter.emit("qa.approved", {"verdict": "user approved"})
        return True, ""

    def validate_with_retries(self, subtask: str, agent_type: str, station: Station) -> str:
        """Run worker, show user the output, retry if they give feedback."""
        print(f"\n  {CYAN}\u25b6{RESET} {BOLD}{agent_type}{RESET} — {subtask[:100]}")
        feedback = ""

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                print(f"    {YELLOW}\u21bb{RESET} Retrying ({attempt}/{MAX_RETRIES})...")
            print(f"    {DIM}Working...{RESET}", end="", flush=True)
            t0 = time.time()
            result = station.run(subtask, agent_type, attempt=attempt, prior_feedback=feedback)
            elapsed = time.time() - t0
            print(f"\r    {GREEN}\u2713{RESET} Done — {len(result):,} chars ({elapsed:.0f}s)")

            approved, feedback = self.check(subtask, result, agent_type)

            if approved:
                return result

            if feedback == "__skip__":
                print(f"    {DIM}Skipped by user.{RESET}")
                return f"[Skipped by user] {subtask}"

        print(f"    {DIM}Max retries reached. Passing best effort to manager.{RESET}")
        return result
