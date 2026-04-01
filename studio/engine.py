"""
Engine — Manager agent orchestration.

The Engine breaks a goal into subtasks, delegates to specialist workers,
validates via the quality gate, and synthesizes the final result.

Uses LLM.call() for all model calls — no SDK-specific interfaces.
"""

import re
from dotenv import load_dotenv

from .llm import LLM
from .events import EventEmitter
from .station import Station, list_available_agents
from .quality_gate import QualityGate
from .permissions import (
    PermissionGuard, ExecutionMode, SpendingGuard,
    OversightMode, EscalationReason,
)
from .audit import AuditLog

load_dotenv()

# ─── ANSI Colors ──────────────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"


def _parse_delegations(text: str, allowed_agents: list[str]) -> list[dict]:
    """Parse delegation instructions from the manager's response.

    Supports formats:
        DELEGATE: [agent-type] subtask description
        DELEGATE: agent-type subtask description
        [agent-type] subtask description
        1. [agent-type] subtask description
    """
    delegations = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        rest = None

        if line.upper().startswith("DELEGATE:"):
            rest = line[len("DELEGATE:"):].strip()
        elif re.match(r"^\d+[.)]\s*\[", line):
            rest = re.sub(r"^\d+[.)]\s*", "", line)
        elif re.match(r"^\d+[.)]\s+\S", line):
            rest = re.sub(r"^\d+[.)]\s*", "", line)
        elif line.startswith("- [") or line.startswith("* ["):
            rest = line[2:].strip()
        elif line.startswith("["):
            rest = line

        if rest is None:
            continue

        # Try bracketed: [agent-type] description
        match = re.match(r"\[([^\]]+)\]\s*(.*)", rest)
        if match:
            agent_type = match.group(1).strip()
            description = match.group(2).strip()
        else:
            # Try unbracketed: agent-type description
            agent_type = None
            description = ""
            for aid in allowed_agents:
                if rest.lower().startswith(aid):
                    agent_type = aid
                    description = rest[len(aid):].strip()
                    break
            if not agent_type:
                continue

        # Strip leading punctuation
        description = re.sub(r"^[-:—]\s*", "", description)

        # Match to allowed agents (exact or partial)
        if agent_type in allowed_agents:
            delegations.append({"agent_type": agent_type, "subtask": description})
        else:
            matched = [a for a in allowed_agents if agent_type in a or a in agent_type]
            if matched:
                delegations.append({"agent_type": matched[0], "subtask": description})

    return delegations


class Engine:
    """Orchestrates specialist agents to achieve a goal."""

    def __init__(
        self,
        llm: LLM = None,
        manager_model: str = "claude-sonnet-4-6",
        worker_model: str = "claude-haiku-4-5-20251001",
        checker_model: str = "claude-haiku-4-5-20251001",
        emitter: EventEmitter = None,
        permissions: PermissionGuard = None,
        spending_guard: SpendingGuard = None,
        audit: AuditLog = None,
        oversight_mode: OversightMode = OversightMode.CEO,
        mcp_bridge=None,
        provider: str = "auto",
    ):
        self.manager_llm = llm or LLM(provider=provider, model=manager_model)
        self.emitter = emitter or EventEmitter()
        self.permissions = permissions or PermissionGuard()
        self.spending = spending_guard or SpendingGuard()
        self.audit = audit or AuditLog()
        self.oversight_mode = oversight_mode
        self.human_approval = (oversight_mode == OversightMode.SUPERVISED)
        self.checkpoints = (oversight_mode == OversightMode.SUPERVISED)
        self.mcp_bridge = mcp_bridge
        self._subtask_count = 0

        worker_llm = LLM(provider=provider, model=worker_model)
        checker_llm = LLM(provider=provider, model=checker_model)

        self.station = Station(
            llm=worker_llm,
            emitter=self.emitter,
            permissions=self.permissions,
            mcp_bridge=mcp_bridge,
        )
        self.quality_gate = QualityGate(
            llm=checker_llm, emitter=self.emitter,
        )

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
        self.emitter.emit("engine.escalation", {"reason": reason.value, **context})

        reason_labels = {
            EscalationReason.DANGEROUS_TOOL: f"{RED}DANGEROUS TOOL{RESET}",
            EscalationReason.PRODUCTION_TARGET: f"{RED}PRODUCTION TARGET{RESET}",
            EscalationReason.SPENDING_THRESHOLD: f"{YELLOW}SPENDING THRESHOLD{RESET}",
            EscalationReason.WORKER_BLOCKER: f"{RED}WORKER BLOCKER{RESET}",
        }
        label = reason_labels.get(reason, reason.value)

        print(f"\n  {RED}{'='*56}{RESET}")
        print(f"  {BOLD}ESCALATION — CEO APPROVAL REQUIRED{RESET}")
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

    def run(self, goal: str, allowed_agents: list[str] = None) -> dict:
        """
        Run the manager agent on a goal.
        Returns {"summary": str, "artifacts": list[dict], "audit_log": str}.
        """
        agents = allowed_agents or list_available_agents()

        self.audit.log_run_start(goal, agents, self.permissions.mode.value)
        self.emitter.emit("engine.started", {"goal": goal, "agents": agents})

        unit = "turns" if self.spending.subscription_mode else "tokens"
        print(f"\n{'='*60}")
        print(f"{BOLD}GOAL:{RESET} {goal[:200]}")
        print(f"{BOLD}Team:{RESET} {', '.join(agents)}")
        print(f"{BOLD}Mode:{RESET} {self.permissions.get_oversight_label()}")
        print(f"{BOLD}Limit:{RESET} {self.spending.max_tokens:,} {unit}")
        print(f"{'='*60}\n")

        # Step 1: Manager breaks goal into subtasks
        print(f"{DIM}Manager is breaking down your task...{RESET}", end="", flush=True)

        manager_system = f"""You are an orchestrating manager. Break the goal into 2-4 focused subtasks.
For each subtask, assign the best specialist from: {agents}

Respond with EXACTLY this format, one per line:
DELEGATE: [agent-type] Clear description of what the specialist must deliver

Nothing else. No commentary. Just the DELEGATE lines."""

        response = self.manager_llm.call(manager_system, goal)
        self.spending.track(response.input_tokens, response.output_tokens)
        self.audit.log_tokens(response.input_tokens, response.output_tokens, "manager")
        print(f"\r{' '*50}\r", end="")

        # Parse delegations
        delegations = _parse_delegations(response.text, agents)

        if not delegations:
            # Fallback: assign the whole goal to the first agent
            delegations = [{"agent_type": agents[0], "subtask": goal}]

        manager_text = response.text
        if delegations:
            print(f"\n{DIM}[Manager]: Breaking into {len(delegations)} subtasks{RESET}")

        # Step 2: Execute each subtask
        results = []
        for delegation in delegations:
            agent_type = delegation["agent_type"]
            subtask = delegation["subtask"]

            # Human approval gate (supervised mode only)
            if self.human_approval:
                approved, subtask = self._request_delegation_approval(subtask, agent_type)
                self.audit.log_approval(f"delegate:{agent_type}", approved, "human review")
                if not approved:
                    results.append(f"[SKIPPED] {agent_type}: {subtask}")
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
                    self.audit.log_run_complete("Stopped by CEO (blocker).", self.spending.tokens_used)
                    log_file = self.audit.save()
                    return {
                        "summary": f"Stopped by CEO after worker blocker.",
                        "artifacts": self.station.artifacts,
                        "audit_log": str(log_file),
                    }
                elif decision != "approve":
                    result += f"\n\n[CEO REDIRECT] {decision}"

            # CEO mode: check spending threshold
            if self.oversight_mode == OversightMode.CEO and self.spending.should_escalate():
                decision = self._escalate(EscalationReason.SPENDING_THRESHOLD, {
                    "tokens_used": f"{self.spending.tokens_used:,}",
                    "max_tokens": f"{self.spending.max_tokens:,}",
                })
                if decision == "deny":
                    self.audit.log_run_complete("Stopped by CEO (spending).", self.spending.tokens_used)
                    log_file = self.audit.save()
                    return {
                        "summary": f"Stopped by CEO at spending threshold.",
                        "artifacts": self.station.artifacts,
                        "audit_log": str(log_file),
                    }

            # SUPERVISED mode: checkpoint
            if self.oversight_mode == OversightMode.SUPERVISED:
                decision = self._checkpoint(agent_type, subtask, result)
                if decision == "stop":
                    self.audit.log_run_complete("Stopped by user.", self.spending.tokens_used)
                    log_file = self.audit.save()
                    return {
                        "summary": f"Stopped by user after {self._subtask_count} subtask(s).",
                        "artifacts": self.station.artifacts,
                        "audit_log": str(log_file),
                    }
                if decision != "continue":
                    result += f"\n\n[USER REDIRECT] {decision}"

            results.append(result)

        # Step 3: Manager synthesizes results
        print(f"\n{DIM}Manager is synthesizing results...{RESET}", end="", flush=True)

        synthesis_prompt = f"""Original goal: {goal[:500]}

Results from {len(results)} specialist(s):

"""
        for i, (delegation, result) in enumerate(zip(delegations, results), 1):
            synthesis_prompt += f"--- {delegation['agent_type']} ---\n{result[:3000]}\n\n"

        synthesis_prompt += """Synthesize these results into a clear, actionable final summary.
Focus on what was accomplished and what the user should do next.
Be concise but complete."""

        synthesis = self.manager_llm.call(
            "You are a project manager. Synthesize the specialist results into a clear final summary.",
            synthesis_prompt,
        )
        self.spending.track(synthesis.input_tokens, synthesis.output_tokens)
        print(f"\r{' '*50}\r", end="")

        summary = synthesis.text
        self.emitter.emit("engine.completed", {"subtasks": len(delegations)})
        self.audit.log_run_complete(summary, self.spending.tokens_used)
        log_file = self.audit.save()

        ok, spend_msg = self.spending.check()
        print(f"\n{GREEN}Done.{RESET} {DIM}{spend_msg} | Audit: {log_file}{RESET}\n")

        return {
            "summary": summary,
            "artifacts": self.station.artifacts,
            "audit_log": str(log_file),
        }
