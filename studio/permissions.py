"""
Permissions — Tool classification and safety layer.

Controls what agents can do based on tool risk level,
execution mode (dry-run vs execute), and oversight mode.

Oversight modes:
    CEO      — Agents run autonomously; human only intervenes for
               dangerous tools, production targets, spending thresholds,
               or worker-flagged blockers.
    SUPERVISED — Legacy mode with checkpoints after every subtask
               and per-delegation approval.
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


class OversightMode(Enum):
    CEO = "ceo"                # Escalation-only: human approves dangerous/prod actions
    SUPERVISED = "supervised"  # Legacy: checkpoints + per-delegation approval


class EscalationReason(Enum):
    DANGEROUS_TOOL = "dangerous_tool"         # Tool classified as DANGEROUS
    PRODUCTION_TARGET = "production_target"   # Non-SAFE tool targeting prod environment
    SPENDING_THRESHOLD = "spending_threshold"  # Token budget crossed 80%
    WORKER_BLOCKER = "worker_blocker"         # Worker flagged a blocker it can't resolve


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
    Enforces tool permissions based on execution mode, risk level,
    and oversight mode.

    CEO mode (default):
        - SAFE tools: always allowed
        - SENSITIVE tools: allowed without approval (routine work)
        - DANGEROUS tools: escalate to human (pause and wait)
        - Any non-SAFE tool targeting prod: escalate to human

    SUPERVISED mode (legacy):
        - Same as original behavior: approve SENSITIVE + DANGEROUS in execute mode

    DRY_RUN always blocks DANGEROUS tools regardless of oversight mode.
    """

    def __init__(self, mode: ExecutionMode = ExecutionMode.DRY_RUN,
                 environment: str = "dev",
                 oversight: OversightMode = OversightMode.CEO):
        self.mode = mode
        self.environment = environment
        self.oversight = oversight
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

        # DRY_RUN mode — dangerous always blocked, regardless of oversight
        if self.mode == ExecutionMode.DRY_RUN:
            if risk == ToolRisk.DANGEROUS:
                return False, (
                    f"[BLOCKED] '{tool_name}' is a dangerous operation. "
                    f"Currently in dry-run mode. Use --execute to enable real actions."
                )
            return True, "ok"

        # EXECUTE mode — branch by oversight mode
        if self.oversight == OversightMode.CEO:
            return self._check_ceo(tool_name, inputs, risk)
        else:
            return self._check_supervised(tool_name, inputs, risk)

    def _check_ceo(self, tool_name: str, inputs: dict, risk: ToolRisk) -> tuple:
        """CEO mode: only escalate for dangerous tools or prod-targeting actions."""
        # SAFE tools: always fine
        if risk == ToolRisk.SAFE:
            return True, "ok"

        # Check session cache
        action_key = f"{tool_name}:{hash(str(inputs))}"
        if action_key in self._approved_actions:
            return True, "previously approved"

        # SENSITIVE tool in non-prod: auto-approved (routine work)
        if risk == ToolRisk.SENSITIVE and self.environment != "prod":
            return True, "ok"

        # Escalation required: DANGEROUS tool, or any non-SAFE tool in prod
        if risk == ToolRisk.DANGEROUS:
            reason = EscalationReason.DANGEROUS_TOOL
        else:
            reason = EscalationReason.PRODUCTION_TARGET

        return self._request_escalation(tool_name, inputs, risk, action_key, reason)

    def _check_supervised(self, tool_name: str, inputs: dict, risk: ToolRisk) -> tuple:
        """SUPERVISED mode: original behavior — approve sensitive + dangerous."""
        if risk == ToolRisk.SAFE:
            return True, "ok"

        action_key = f"{tool_name}:{hash(str(inputs))}"
        if action_key in self._approved_actions:
            return True, "previously approved"

        return self._request_approval(tool_name, inputs, risk, action_key)

    def _request_escalation(self, tool_name: str, inputs: dict, risk: ToolRisk,
                            action_key: str, reason: EscalationReason) -> tuple:
        """
        CEO escalation — agent pauses and waits for human decision.
        Shows why escalation was triggered and what the agent wants to do.
        """
        reason_labels = {
            EscalationReason.DANGEROUS_TOOL: "\033[31mDANGEROUS TOOL\033[0m",
            EscalationReason.PRODUCTION_TARGET: "\033[31mPRODUCTION TARGET\033[0m",
        }
        label = reason_labels.get(reason, str(reason.value))

        print(f"\n{'='*60}")
        print(f"  \033[31m⚠  ESCALATION — CEO APPROVAL REQUIRED\033[0m")
        print(f"  Reason: {label}")
        print(f"{'='*60}")
        print(f"  Tool:        {tool_name}")
        print(f"  Risk:        {risk.value}")
        print(f"  Environment: {self.environment}")
        print(f"  Inputs:      {str(inputs)[:200]}")

        if self.environment == "prod":
            print(f"\n  \033[31m⚠  This action targets PRODUCTION.\033[0m")

        print(f"{'='*60}")
        print(f"  [Y] Approve   [n] Deny   [m] Modify inputs")

        response = input("  Decision: ").strip().lower()
        if response in ("y", "yes", ""):
            self._approved_actions.add(action_key)
            return True, "approved by CEO"
        elif response in ("m", "modify"):
            modification = input("  New instructions: ").strip()
            return False, f"[MODIFY] {modification}"

        return False, "denied by CEO"

    def _request_approval(self, tool_name: str, inputs: dict, risk: ToolRisk, action_key: str) -> tuple:
        """Legacy approval prompt for SUPERVISED mode."""
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

    def get_oversight_label(self) -> str:
        """Human-readable label for the oversight mode."""
        if self.oversight == OversightMode.CEO:
            return "\033[32mCEO MODE\033[0m (autonomous — escalates only for critical actions)"
        return "\033[33mSUPERVISED MODE\033[0m (checkpoints + per-task approval)"


class SpendingGuard:
    """
    Tracks and limits API token usage per run.
    Aborts if spending exceeds the cap.
    In CEO mode, escalates once when the threshold (80%) is crossed.
    """

    def __init__(self, max_tokens: int = 100_000, threshold: float = 0.8):
        self.max_tokens = max_tokens
        self.tokens_used = 0
        self.threshold = threshold
        self._threshold_escalated = False

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

    def should_escalate(self) -> bool:
        """Returns True once when spending crosses the threshold but hasn't hit the hard cap."""
        if self._threshold_escalated:
            return False
        if self.tokens_used >= (self.max_tokens * self.threshold) and self.tokens_used < self.max_tokens:
            self._threshold_escalated = True
            return True
        return False

    @property
    def remaining(self) -> int:
        return max(0, self.max_tokens - self.tokens_used)
