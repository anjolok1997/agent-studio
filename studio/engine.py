"""
Engine — Manager agent orchestration.

The Engine is the top-level entry point. It breaks a goal into subtasks,
delegates to specialist workers, validates via the quality gate,
and synthesizes the final result.

Oversight modes:
    CEO        — Agents run autonomously. Human only intervenes for
                 dangerous tools, production targets, spending thresholds,
                 or worker-flagged blockers.
    SUPERVISED — Legacy mode with checkpoints and per-delegation approval.
"""

import os
from anthropic import Anthropic
from dotenv import load_dotenv

from .events import EventEmitter
from .station import Station, list_available_agents
from .quality_gate import QualityGate
from .permissions import (
    PermissionGuard, ExecutionMode, SpendingGuard,
    OversightMode, EscalationReason,
)
from .audit import AuditLog

try:
    from .mcp_bridge import MCPBridge
except ImportError:
    MCPBridge = None

load_dotenv()

# ─── ANSI Colors ──────────────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"


class Engine:
    """Orchestrates specialist agents to achieve a goal."""

    def __init__(
        self,
        client: Anthropic = None,
        manager_model: str = "claude-sonnet-4-6",
        worker_model: str = "claude-haiku-4-5-20251001",
        checker_model: str = "claude-haiku-4-5-20251001",
        emitter: EventEmitter = None,
        permissions: PermissionGuard = None,
        spending_guard: SpendingGuard = None,
        audit: AuditLog = None,
        oversight_mode: OversightMode = OversightMode.CEO,
        mcp_bridge=None,
    ):
        self.client = client or Anthropic()
        self.manager_model = manager_model
        self.emitter = emitter or EventEmitter()
        self.permissions = permissions or PermissionGuard()
        self.spending = spending_guard or SpendingGuard()
        self.audit = audit or AuditLog()
        self.oversight_mode = oversight_mode
        # Derive legacy flags from oversight mode
        self.human_approval = (oversight_mode == OversightMode.SUPERVISED)
        self.checkpoints = (oversight_mode == OversightMode.SUPERVISED)
        self.mcp_bridge = mcp_bridge
        self._subtask_count = 0
        self.station = Station(
            self.client, worker_model=worker_model,
            emitter=self.emitter, permissions=self.permissions,
            mcp_bridge=mcp_bridge,
        )
        self.quality_gate = QualityGate(
            self.client, checker_model=checker_model, emitter=self.emitter,
        )

    def _build_tools(self, allowed_agents: list[str] = None) -> list[dict]:
        """Build manager tools, optionally restricted to specific agents."""
        agents = allowed_agents or list_available_agents()
        return [
            {
                "name": "delegate_task",
                "description": (
                    "Delegate a focused subtask to the right specialist agent. "
                    "The specialist will complete the work and a QA agent will validate it. "
                    f"Available agent types: {agents}"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "subtask": {
                            "type": "string",
                            "description": "Clear, self-contained description of what the specialist must deliver",
                        },
                        "agent_type": {
                            "type": "string",
                            "enum": agents,
                            "description": "Which specialist to assign this subtask to",
                        },
                    },
                    "required": ["subtask", "agent_type"],
                },
            },
        ]

    def _request_delegation_approval(self, subtask: str, agent_type: str) -> bool:
        """Ask the human to approve a subtask delegation."""
        print(f"\n  {YELLOW}{'─'*56}{RESET}")
        print(f"  {BOLD}Delegation Request{RESET}")
        print(f"  {CYAN}Agent:{RESET}   {agent_type}")
        print(f"  {CYAN}Task:{RESET}    {subtask[:200]}")
        print(f"  {YELLOW}{'─'*56}{RESET}")

        response = input(f"  {BOLD}Approve? [Y/n/edit]: {RESET}").strip().lower()

        if response in ("n", "no"):
            return False, subtask
        if response in ("e", "edit"):
            new_task = input(f"  {BOLD}Revised task:{RESET}\n  > ").strip()
            return True, new_task if new_task else subtask
        return True, subtask

    def _checkpoint(self, agent_type: str, subtask: str, result: str) -> str:
        """
        Checkpoint after a subtask completes. Shows the result and lets the
        user continue, stop, or redirect.
        Returns: "continue", "stop", or a revised instruction string.
        """
        if not self.checkpoints:
            return "continue"

        self._subtask_count += 1
        ok, spend_msg = self.spending.check()

        print(f"\n  {GREEN}{'─'*56}{RESET}")
        print(f"  {BOLD}Checkpoint — Subtask {self._subtask_count} complete{RESET}")
        print(f"  {CYAN}Agent:{RESET}   {agent_type}")
        print(f"  {CYAN}Task:{RESET}    {subtask[:120]}")
        print(f"  {CYAN}Output:{RESET}  {result[:200]}{'...' if len(result) > 200 else ''}")
        print(f"  {DIM}{spend_msg}{RESET}")
        print(f"  {GREEN}{'─'*56}{RESET}")

        response = input(f"  {BOLD}Continue? [Y/n/redirect]: {RESET}").strip().lower()

        if response in ("n", "no", "stop"):
            return "stop"
        if response in ("r", "redirect"):
            redirect = input(f"  {BOLD}New direction for remaining tasks:{RESET}\n  > ").strip()
            return redirect if redirect else "continue"
        return "continue"

    def _escalate(self, reason: EscalationReason, context: dict) -> str:
        """
        CEO escalation — pause execution and wait for human decision.
        Returns: "approve", "deny", or a modified instruction string.
        """
        self.emitter.emit("engine.escalation", {"reason": reason.value, **context})

        reason_labels = {
            EscalationReason.DANGEROUS_TOOL: f"{RED}DANGEROUS TOOL{RESET}",
            EscalationReason.PRODUCTION_TARGET: f"{RED}PRODUCTION TARGET{RESET}",
            EscalationReason.SPENDING_THRESHOLD: f"{YELLOW}SPENDING THRESHOLD{RESET}",
            EscalationReason.WORKER_BLOCKER: f"{RED}WORKER BLOCKER{RESET}",
        }
        label = reason_labels.get(reason, reason.value)

        print(f"\n  {RED}{'='*56}{RESET}")
        print(f"  {BOLD}⚠  ESCALATION — CEO APPROVAL REQUIRED{RESET}")
        print(f"  {BOLD}Reason:{RESET} {label}")
        print(f"  {RED}{'='*56}{RESET}")

        for key, value in context.items():
            print(f"  {CYAN}{key}:{RESET}  {str(value)[:200]}")

        print(f"  {RED}{'='*56}{RESET}")
        print(f"  [{GREEN}Y{RESET}] Approve   [{RED}n{RESET}] Deny   [{YELLOW}m{RESET}] Modify")

        response = input(f"  {BOLD}Decision: {RESET}").strip().lower()

        if response in ("n", "no", "deny"):
            self.audit.log_escalation(reason.value, context, "denied")
            return "deny"
        elif response in ("m", "modify"):
            modification = input(f"  {BOLD}New instructions: {RESET}").strip()
            self.audit.log_escalation(reason.value, context, f"modified: {modification}")
            return modification if modification else "approve"

        self.audit.log_escalation(reason.value, context, "approved")
        return "approve"

    def _check_spending(self, response) -> bool:
        """Track tokens and check spending limit."""
        if hasattr(response, "usage"):
            self.spending.track(response.usage.input_tokens, response.usage.output_tokens)
            self.audit.log_tokens(
                response.usage.input_tokens,
                response.usage.output_tokens,
                self.manager_model,
            )
        ok, msg = self.spending.check()
        if not ok:
            print(f"\n  {RED}{msg}{RESET}")
            return False
        return True

    def run(self, goal: str, allowed_agents: list[str] = None) -> dict:
        """
        Run the manager agent on a goal.
        Returns {"summary": str, "artifacts": list[dict], "audit_log": str}.
        """
        agents = allowed_agents or list_available_agents()
        tools = self._build_tools(agents)

        self.audit.log_run_start(goal, agents, self.permissions.mode.value)
        self.emitter.emit("engine.started", {"goal": goal, "agents": agents})

        print(f"\n{'='*60}")
        print(f"{BOLD}GOAL:{RESET} {goal}")
        print(f"{BOLD}Team:{RESET} {', '.join(agents)}")
        print(f"{BOLD}Mode:{RESET} {self.permissions.get_mode_label()}")
        print(f"{BOLD}Oversight:{RESET} {self.permissions.get_oversight_label()}")
        print(f"{BOLD}Spending limit:{RESET} {self.spending.max_tokens:,} tokens")
        print(f"{'='*60}\n")

        system = f"""You are an orchestrating manager agent. When given a goal:
1. Break it into 2-4 focused subtasks.
2. For each subtask, pick the right specialist from: {agents}
3. Use delegate_task to assign each subtask — work sequentially, one at a time.
4. After all workers finish, synthesize their results into a final project summary.

Choosing the right specialist matters. Pick the best fit for each subtask."""

        messages = [{"role": "user", "content": goal}]

        for iteration in range(12):
            self.emitter.emit("engine.iteration", {"iteration": iteration + 1})

            response = self.client.messages.create(
                model=self.manager_model,
                max_tokens=2048,
                system=system,
                tools=tools,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            if not self._check_spending(response):
                break

            if response.stop_reason == "end_turn":
                summary = next(
                    (b.text for b in response.content if hasattr(b, "text")),
                    "(no summary)"
                )
                self.emitter.emit("engine.completed", {"iterations": iteration + 1})
                self.audit.log_run_complete(summary, self.spending.tokens_used)
                log_file = self.audit.save()
                print(f"\nMANAGER DONE after {iteration + 1} iteration(s).")
                print(f"{DIM}Tokens used: {self.spending.tokens_used:,} | Audit log: {log_file}{RESET}\n")
                return {
                    "summary": summary,
                    "artifacts": self.station.artifacts,
                    "audit_log": str(log_file),
                }

            tool_results = []
            for block in response.content:
                if hasattr(block, "text") and block.text:
                    print(f"[Manager]: {block.text}")
                if block.type != "tool_use":
                    continue

                subtask = block.input["subtask"]
                agent_type = block.input["agent_type"]

                # Human approval gate
                if self.human_approval:
                    approved, subtask = self._request_delegation_approval(subtask, agent_type)
                    self.audit.log_approval(f"delegate:{agent_type}", approved, "human review")
                    if not approved:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": "[SKIPPED] User chose to skip this subtask.",
                        })
                        continue

                self.emitter.emit("engine.delegating", {
                    "subtask": subtask[:80],
                    "agent_type": agent_type,
                })
                self.audit.log_delegation(subtask, agent_type)

                result = self.quality_gate.validate_with_retries(
                    subtask=subtask,
                    agent_type=agent_type,
                    station=self.station,
                )

                # CEO mode: check for worker blocker escalation
                if self.oversight_mode == OversightMode.CEO and "[ESCALATION:BLOCKER]" in result:
                    decision = self._escalate(EscalationReason.WORKER_BLOCKER, {
                        "agent": agent_type,
                        "subtask": subtask[:120],
                        "blocker": result[:300],
                    })
                    if decision == "deny":
                        print(f"\n{YELLOW}Stopped by CEO after worker blocker.{RESET}")
                        self.audit.log_run_complete("Stopped by CEO (blocker).", self.spending.tokens_used)
                        log_file = self.audit.save()
                        return {
                            "summary": f"Stopped by CEO after worker blocker in subtask '{subtask[:80]}'.",
                            "artifacts": self.station.artifacts,
                            "audit_log": str(log_file),
                        }
                    elif decision != "approve":
                        result += f"\n\n[CEO REDIRECT] {decision}"

                # CEO mode: check spending threshold escalation
                if self.oversight_mode == OversightMode.CEO and self.spending.should_escalate():
                    decision = self._escalate(EscalationReason.SPENDING_THRESHOLD, {
                        "tokens_used": f"{self.spending.tokens_used:,}",
                        "max_tokens": f"{self.spending.max_tokens:,}",
                        "percent": f"{self.spending.tokens_used / self.spending.max_tokens:.0%}",
                    })
                    if decision == "deny":
                        print(f"\n{YELLOW}Stopped by CEO at spending threshold.{RESET}")
                        self.audit.log_run_complete("Stopped by CEO (spending).", self.spending.tokens_used)
                        log_file = self.audit.save()
                        return {
                            "summary": f"Stopped by CEO at spending threshold ({self.spending.tokens_used:,} tokens).",
                            "artifacts": self.station.artifacts,
                            "audit_log": str(log_file),
                        }

                # SUPERVISED mode: checkpoint after every subtask
                if self.oversight_mode == OversightMode.SUPERVISED:
                    decision = self._checkpoint(agent_type, subtask, result)
                    if decision == "stop":
                        print(f"\n{YELLOW}Stopped by user after subtask {self._subtask_count}.{RESET}")
                        self.audit.log_run_complete("Stopped by user.", self.spending.tokens_used)
                        log_file = self.audit.save()
                        print(f"{DIM}Tokens used: {self.spending.tokens_used:,} | Audit log: {log_file}{RESET}\n")
                        return {
                            "summary": f"Stopped by user after {self._subtask_count} subtask(s). Partial results collected.",
                            "artifacts": self.station.artifacts,
                            "audit_log": str(log_file),
                        }
                    if decision != "continue":
                        result += f"\n\n[USER REDIRECT] The user wants to change direction: {decision}"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})

        self.audit.log_run_complete("Manager hit iteration limit.", self.spending.tokens_used)
        self.audit.save()
        return {"summary": "Manager hit iteration limit.", "artifacts": self.station.artifacts}
