"""
Permissions — Tool classification and safety layer.

Controls what agents can do based on tool risk level,
execution mode (dry-run vs execute), and human approval.
"""

import os
from enum import Enum


class ToolRisk(Enum):
    SAFE = "safe"              # Read-only: research, summarize, analyze
    SENSITIVE = "sensitive"    # Creates artifacts: draft_output, create_file
    DANGEROUS = "dangerous"    # Infrastructure: run_sql, deploy, shell_exec


class ExecutionMode(Enum):
    DRY_RUN = "dry-run"       # Plan only — no real actions (default)
    EXECUTE = "execute"        # Real actions — requires approval per step


# Tool risk classification
TOOL_RISK_MAP = {
    # Built-in tools
    "research": ToolRisk.SAFE,
    "draft_output": ToolRisk.SENSITIVE,
    "flag_blocker": ToolRisk.SAFE,
    # Future tools — classified ahead of time
    "read_file": ToolRisk.SAFE,
    "write_file": ToolRisk.SENSITIVE,
    "run_sql": ToolRisk.DANGEROUS,
    "run_shell": ToolRisk.DANGEROUS,
    "terraform_plan": ToolRisk.SENSITIVE,
    "terraform_apply": ToolRisk.DANGEROUS,
    "deploy": ToolRisk.DANGEROUS,
    "send_message": ToolRisk.SENSITIVE,
    "call_api": ToolRisk.SENSITIVE,
}


class PermissionGuard:
    """
    Enforces tool permissions based on execution mode and risk level.

    In DRY_RUN mode (default):
        - SAFE tools: allowed
        - SENSITIVE tools: allowed (artifacts stay in memory)
        - DANGEROUS tools: blocked with explanation

    In EXECUTE mode:
        - SAFE tools: allowed
        - SENSITIVE tools: requires human approval
        - DANGEROUS tools: requires human approval + environment check
    """

    def __init__(self, mode: ExecutionMode = ExecutionMode.DRY_RUN, environment: str = "dev"):
        self.mode = mode
        self.environment = environment
        self._approved_actions: set = set()

    def classify(self, tool_name: str) -> ToolRisk:
        """Get the risk level of a tool."""
        return TOOL_RISK_MAP.get(tool_name, ToolRisk.SENSITIVE)

    def check(self, tool_name: str, inputs: dict) -> tuple:
        """
        Check if a tool call is allowed.
        Returns (allowed: bool, reason: str).
        """
        risk = self.classify(tool_name)

        # DRY_RUN mode
        if self.mode == ExecutionMode.DRY_RUN:
            if risk == ToolRisk.DANGEROUS:
                return False, (
                    f"[BLOCKED] '{tool_name}' is a dangerous operation. "
                    f"Currently in dry-run mode. Use --execute to enable real actions."
                )
            return True, "ok"

        # EXECUTE mode
        if risk == ToolRisk.SAFE:
            return True, "ok"

        # Check if already approved this session
        action_key = f"{tool_name}:{hash(str(inputs))}"
        if action_key in self._approved_actions:
            return True, "previously approved"

        # Require human approval for sensitive/dangerous tools
        return self._request_approval(tool_name, inputs, risk, action_key)

    def _request_approval(self, tool_name: str, inputs: dict, risk: ToolRisk, action_key: str) -> tuple:
        """Ask the human to approve a sensitive/dangerous action."""
        risk_label = f"\033[33mSENSITIVE\033[0m" if risk == ToolRisk.SENSITIVE else f"\033[31mDANGEROUS\033[0m"

        print(f"\n{'='*60}")
        print(f"  APPROVAL REQUIRED — {risk_label}")
        print(f"{'='*60}")
        print(f"  Tool:        {tool_name}")
        print(f"  Risk:        {risk.value}")
        print(f"  Environment: {self.environment}")
        print(f"  Inputs:      {str(inputs)[:200]}")

        if risk == ToolRisk.DANGEROUS and self.environment == "prod":
            print(f"\n  \033[31mWARNING: This is a DANGEROUS action targeting PRODUCTION.\033[0m")

        print(f"{'='*60}")

        response = input("  Approve? [y/N]: ").strip().lower()
        if response in ("y", "yes"):
            self._approved_actions.add(action_key)
            return True, "approved by user"

        return False, "denied by user"

    def get_mode_label(self) -> str:
        """Human-readable label for the current mode."""
        if self.mode == ExecutionMode.DRY_RUN:
            return "\033[36mDRY-RUN\033[0m (planning only, no real actions)"
        return f"\033[33mEXECUTE\033[0m (environment: {self.environment})"


class SpendingGuard:
    """
    Tracks and limits API token usage per run.
    Aborts if spending exceeds the cap.
    """

    def __init__(self, max_tokens: int = 100_000):
        self.max_tokens = max_tokens
        self.tokens_used = 0

    def track(self, input_tokens: int, output_tokens: int):
        """Record token usage from an API call."""
        self.tokens_used += input_tokens + output_tokens

    def check(self) -> tuple:
        """Check if we're within budget. Returns (ok: bool, message: str)."""
        if self.tokens_used >= self.max_tokens:
            return False, (
                f"Spending cap reached: {self.tokens_used:,} / {self.max_tokens:,} tokens. "
                f"Run aborted to prevent excessive API costs."
            )
        return True, f"{self.tokens_used:,} / {self.max_tokens:,} tokens used"

    @property
    def remaining(self) -> int:
        return max(0, self.max_tokens - self.tokens_used)
