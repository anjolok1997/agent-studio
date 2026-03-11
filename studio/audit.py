"""
Audit — Logging every agent run for traceability.

Records goals, agents used, outputs, token usage, and approvals
to a local JSON log file.
"""

import json
import time
from pathlib import Path
from datetime import datetime


AUDIT_DIR = Path(__file__).resolve().parent.parent / "logs"


class AuditLog:
    """Append-only audit log for agent runs."""

    def __init__(self, log_dir: Path = None):
        self.log_dir = log_dir or AUDIT_DIR
        self.log_dir.mkdir(exist_ok=True)
        self._entries = []
        self._run_id = f"run_{int(time.time())}"
        self._start_time = datetime.now().isoformat()

    def log(self, event_type: str, data: dict):
        """Add an entry to the audit log."""
        entry = {
            "run_id": self._run_id,
            "timestamp": datetime.now().isoformat(),
            "event": event_type,
            "data": data,
        }
        self._entries.append(entry)

    def log_run_start(self, goal: str, agents: list, mode: str):
        self.log("run.started", {
            "goal": goal,
            "agents": agents,
            "mode": mode,
        })

    def log_delegation(self, subtask: str, agent_type: str):
        self.log("task.delegated", {
            "subtask": subtask,
            "agent_type": agent_type,
        })

    def log_approval(self, tool_name: str, approved: bool, reason: str):
        self.log("permission.check", {
            "tool": tool_name,
            "approved": approved,
            "reason": reason,
        })

    def log_qa_result(self, subtask: str, approved: bool, attempt: int):
        self.log("qa.result", {
            "subtask": subtask[:100],
            "approved": approved,
            "attempt": attempt,
        })

    def log_tokens(self, input_tokens: int, output_tokens: int, model: str):
        self.log("tokens.used", {
            "input": input_tokens,
            "output": output_tokens,
            "model": model,
        })

    def log_run_complete(self, summary: str, total_tokens: int):
        self.log("run.completed", {
            "summary_length": len(summary),
            "total_tokens": total_tokens,
        })

    def save(self):
        """Write the audit log to disk."""
        log_file = self.log_dir / f"{self._run_id}.json"
        log_data = {
            "run_id": self._run_id,
            "started": self._start_time,
            "completed": datetime.now().isoformat(),
            "entries": self._entries,
        }
        log_file.write_text(json.dumps(log_data, indent=2))
        return log_file
