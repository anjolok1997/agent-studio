"""
Engine — Manager agent orchestration.

The Engine breaks a goal into subtasks, delegates to specialist workers,
validates via the quality gate, and synthesizes the final result.

Uses LLM.call() for all model calls — no SDK-specific interfaces.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _parse_single_delegation(rest: str, allowed_agents: list[str]) -> dict | None:
    """Parse a single delegation line into {agent_type, subtask} or None."""
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
            return None

    # Strip leading punctuation
    description = re.sub(r"^[-:—]\s*", "", description)

    # Match to allowed agents (exact or partial)
    if agent_type in allowed_agents:
        return {"agent_type": agent_type, "subtask": description}
    matched = [a for a in allowed_agents if agent_type in a or a in agent_type]
    if matched:
        return {"agent_type": matched[0], "subtask": description}
    return None


def _extract_delegation_line(line: str) -> tuple[str | None, bool]:
    """Extract the rest of a delegation line and whether it's parallel.

    Returns (rest, is_parallel) or (None, False) if not a delegation.
    """
    if line.upper().startswith("PARALLEL:"):
        return line[len("PARALLEL:"):].strip(), True
    if line.upper().startswith("DELEGATE:"):
        return line[len("DELEGATE:"):].strip(), False
    if re.match(r"^\d+[.)]\s*\[", line):
        return re.sub(r"^\d+[.)]\s*", "", line), False
    if re.match(r"^\d+[.)]\s+\S", line):
        return re.sub(r"^\d+[.)]\s*", "", line), False
    if line.startswith("- [") or line.startswith("* ["):
        return line[2:].strip(), False
    if line.startswith("["):
        return line, False
    return None, False


def _parse_delegations(text: str, allowed_agents: list[str]) -> list[dict]:
    """Parse delegation instructions from the manager's response.

    Supports formats:
        DELEGATE: [agent-type] subtask description   (sequential)
        PARALLEL: [agent-type] subtask description    (run concurrently)

    Returns list of dicts, each with 'agent_type', 'subtask', and 'parallel' (bool).
    """
    delegations = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        rest, is_parallel = _extract_delegation_line(line)
        if rest is None:
            continue

        parsed = _parse_single_delegation(rest, allowed_agents)
        if parsed:
            parsed["parallel"] = is_parallel
            delegations.append(parsed)

    return delegations


class Engine:
    """Orchestrates specialist agents to achieve a goal."""

    def __init__(
        self,
        llm: LLM = None,
        manager_model: str = "claude-sonnet-4-6",
        worker_model: str = "claude-haiku-4-5-20251001",
        emitter: EventEmitter = None,
        permissions: PermissionGuard = None,
        spending_guard: SpendingGuard = None,
        audit: AuditLog = None,
        oversight_mode: OversightMode = OversightMode.CEO,
        mcp_bridge=None,
        provider: str = "auto",
        mcp_config_path: str = None,
        use_claude_integrations: bool = False,
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

        worker_llm = LLM(provider=provider, model=worker_model,
                         mcp_config_path=mcp_config_path,
                         use_claude_integrations=use_claude_integrations)

        self.station = Station(
            llm=worker_llm,
            emitter=self.emitter,
            permissions=self.permissions,
            mcp_bridge=mcp_bridge,
        )
        self.quality_gate = QualityGate(emitter=self.emitter)

    def _show_spending(self):
        """Print live spending status and any new warnings."""
        warning = self.spending.get_warning()
        if warning:
            print(f"\n  {YELLOW}⚠ {warning}{RESET}")
        print(f"  {DIM}{self.spending.status_line()}{RESET}")

    def _summarize_result(self, agent_type: str, result: str) -> str:
        """Summarize a worker's output to save tokens in downstream context."""
        if len(result) <= 500:
            return result
        # Ask haiku for a quick summary instead of forwarding raw text
        summary_response = self.manager_llm.call(
            "Summarize this output in 2-3 sentences. Keep key facts, data, and decisions.",
            f"Output from {agent_type}:\n{result[:3000]}",
            max_tokens=256,
        )
        self.spending.track(summary_response.input_tokens, summary_response.output_tokens)
        return summary_response.text.strip()

    def _build_worker_prompt(self, subtask: str, completed: list[tuple]) -> str:
        """Add summarized prior results as context so workers can build on each other."""
        if not completed:
            return subtask
        context_parts = []
        for prev_agent, prev_task, prev_result in completed:
            # Use summary for large outputs, raw text for small ones
            if len(prev_result) > 500:
                summary = self._summarize_result(prev_agent, prev_result)
                context_parts.append(
                    f"--- Summary from {prev_agent} ({prev_task[:80]}) ---\n{summary}"
                )
            else:
                context_parts.append(
                    f"--- Output from {prev_agent} ({prev_task[:80]}) ---\n{prev_result}"
                )
        return (
            f"{subtask}\n\n"
            f"CONTEXT FROM PREVIOUS WORK:\n"
            f"{''.join(context_parts)}"
        )

    def _run_single(self, delegation: dict, agents: list[str],
                    conversation: list[str], completed: list[tuple]) -> str | None:
        """Execute a single sequential delegation. Returns result or None if stopped."""
        agent_type = delegation["agent_type"]
        subtask = delegation["subtask"]

        # Human approval gate (supervised mode only)
        if self.human_approval:
            approved, subtask = self._request_delegation_approval(subtask, agent_type)
            self.audit.log_approval(f"delegate:{agent_type}", approved, "human review")
            if not approved:
                conversation.append(f"[Result] {agent_type} was skipped by user.")
                return ""

        self.emitter.emit("engine.delegating", {
            "subtask": subtask[:80], "agent_type": agent_type,
        })
        self.audit.log_delegation(subtask, agent_type)

        # Give the worker context from prior results
        worker_prompt = self._build_worker_prompt(subtask, completed)

        result = self.quality_gate.validate_with_retries(
            subtask=worker_prompt, agent_type=agent_type, station=self.station,
        )

        # Track worker tokens
        self.spending.track(self.station.last_input_tokens, self.station.last_output_tokens)
        self._show_spending()

        completed.append((agent_type, subtask, result))
        conversation.append(f"DELEGATE: [{agent_type}] {subtask}")
        conversation.append(f"[Result from {agent_type}]: {result[:2000]}")
        return result

    def _run_parallel(self, batch: list[dict], agents: list[str],
                      conversation: list[str], completed: list[tuple]) -> list[str] | None:
        """Execute a batch of independent delegations concurrently."""
        print(f"\n  {CYAN}Running {len(batch)} tasks in parallel...{RESET}")

        # Human approval gate (supervised mode only)
        approved_batch = []
        for delegation in batch:
            agent_type = delegation["agent_type"]
            subtask = delegation["subtask"]
            if self.human_approval:
                approved, subtask = self._request_delegation_approval(subtask, agent_type)
                self.audit.log_approval(f"delegate:{agent_type}", approved, "human review")
                if not approved:
                    conversation.append(f"[Result] {agent_type} was skipped by user.")
                    continue
            approved_batch.append({"agent_type": agent_type, "subtask": subtask})

        if not approved_batch:
            return []

        for d in approved_batch:
            self.emitter.emit("engine.delegating", {
                "subtask": d["subtask"][:80], "agent_type": d["agent_type"],
            })
            self.audit.log_delegation(d["subtask"], d["agent_type"])

        # Run workers concurrently — each gets its own Station for thread safety
        results = {}
        worker_stations = {}
        with ThreadPoolExecutor(max_workers=len(approved_batch)) as pool:
            future_to_task = {}
            for d in approved_batch:
                worker_station = Station(
                    llm=self.station.llm,
                    emitter=self.emitter,
                    permissions=self.permissions,
                    mcp_bridge=self.station.mcp_bridge,
                )
                worker_stations[d["agent_type"]] = worker_station
                future = pool.submit(
                    self.quality_gate.validate_with_retries,
                    subtask=d["subtask"],
                    agent_type=d["agent_type"],
                    station=worker_station,
                )
                future_to_task[future] = d

            for future in as_completed(future_to_task):
                d = future_to_task[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = f"[ERROR] {d['agent_type']} failed: {e}"
                results[d["agent_type"]] = (d["subtask"], result)

        # Collect artifacts and tokens from all parallel worker stations
        for station in worker_stations.values():
            self.station.artifacts.extend(station.artifacts)
            self.spending.track(station.last_input_tokens, station.last_output_tokens)

        # Feed all results back to conversation
        for agent_type, (subtask, result) in results.items():
            completed.append((agent_type, subtask, result))
            conversation.append(f"PARALLEL: [{agent_type}] {subtask}")
            conversation.append(f"[Result from {agent_type}]: {result[:2000]}")

        print(f"  {GREEN}All {len(results)} parallel tasks complete.{RESET}")
        self._show_spending()
        return list(results.values())

    def _request_delegation_approval(self, subtask: str, agent_type: str) -> tuple[bool, str]:
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

    def run(self, goal: str, allowed_agents: list[str] = None, briefing_context: str = None) -> dict:
        """
        Run the manager agent on a goal.
        Returns {"summary": str, "artifacts": list[dict], "audit_log": str}.
        """
        import time
        run_start = time.time()

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

        # ─── Iterative Manager Loop ─────────────────────────────────────
        # Manager delegates one subtask at a time. After each worker finishes,
        # the manager sees the result and decides what's next. This produces
        # better results than planning all subtasks upfront.

        manager_system = f"""You are an orchestrating manager. You coordinate specialists to achieve a goal.

Available specialists: {agents}
"""
        if briefing_context:
            manager_system += """
You already discussed the approach with the user in a briefing session. The
transcript is in your context. Use their preferences and decisions to guide
your delegation. Do not re-ask questions that were already resolved.
"""
        manager_system += """
WORKFLOW:
1. Look at the goal (and any previous results)
2. Decide what to delegate next
3. For sequential work (needs prior results):
     DELEGATE: [agent-type] Description of what they must deliver
4. For independent work (can run at the same time):
     PARALLEL: [agent-type] Task for first specialist
     PARALLEL: [agent-type] Task for second specialist
5. After seeing results, decide the next step
6. When all work is done, respond with: DONE: followed by your final summary

RULES:
- Use PARALLEL: when tasks don't depend on each other — this runs them simultaneously and saves time
- Use DELEGATE: when a task needs results from a previous step
- You can mix: PARALLEL a batch, then DELEGATE a follow-up that uses their results
- When you have enough results, write DONE: and synthesize everything
- Typically 2-4 subtasks total"""

        conversation = []
        if briefing_context:
            conversation.append(briefing_context)
        conversation.append(f"GOAL: {goal}")
        completed = []  # list of (agent_type, subtask, result)
        summary = ""

        for iteration in range(8):  # max 8 iterations
            # Build the prompt — keep goal + briefing, but only last 4 conversation entries
            # to avoid resending the entire history every turn
            core = conversation[:2]  # goal (+ briefing if present)
            recent = conversation[2:][-4:] if len(conversation) > 2 else []
            prompt = "\n\n".join(core + recent)
            if completed:
                prompt += "\n\nWhat's the next step? Respond with DELEGATE:, PARALLEL:, or DONE:"
            else:
                prompt += "\n\nBreak this down. What should the specialists work on? Use PARALLEL: for independent tasks."

            print(f"\n{DIM}Manager is thinking...{RESET}", end="", flush=True)
            response = self.manager_llm.call(manager_system, prompt)
            self.spending.track(response.input_tokens, response.output_tokens)
            self.audit.log_tokens(response.input_tokens, response.output_tokens, "manager")
            print(f"\r{' '*50}\r", end="")

            manager_text = response.text.strip()

            # Check if manager says DONE
            if "DONE:" in manager_text.upper():
                # Extract summary after DONE:
                done_idx = manager_text.upper().index("DONE:")
                summary = manager_text[done_idx + 5:].strip()
                if not summary:
                    summary = manager_text
                break

            # Parse delegation
            delegations = _parse_delegations(manager_text, agents)

            if not delegations:
                # If no delegation found but we have results, treat as done
                if completed:
                    summary = manager_text
                    break
                # First iteration with no delegation — try once more with clearer prompt
                conversation.append(f"[System] Please respond with DELEGATE: [agent-type] description")
                continue

            # Show what the manager decided (reasoning before delegations)
            first_keyword = "PARALLEL:" if delegations[0].get("parallel") else "DELEGATE:"
            if manager_text and not manager_text.upper().startswith(first_keyword):
                reasoning = re.split(r"(?:DELEGATE|PARALLEL):", manager_text, maxsplit=1)[0].strip()
                if reasoning:
                    print(f"\n{DIM}[Manager]: {reasoning[:200]}{RESET}")

            # Split into parallel batch and sequential
            parallel_batch = [d for d in delegations if d.get("parallel")]
            sequential = [d for d in delegations if not d.get("parallel")]

            # If we have a parallel batch, run them concurrently
            if parallel_batch:
                batch_results = self._run_parallel(parallel_batch, agents, conversation, completed)
                if batch_results is None:
                    # Stopped by escalation
                    break
            # Otherwise run the first sequential delegation
            elif sequential:
                delegation = sequential[0]
                single_result = self._run_single(delegation, agents, conversation, completed)
                if single_result is None:
                    break

            # CEO mode: check for worker blocker escalation
            if self.oversight_mode == OversightMode.CEO and completed:
                last_agent, last_subtask, last_result = completed[-1]
                if "[ESCALATION:BLOCKER]" in last_result:
                    decision = self._escalate(EscalationReason.WORKER_BLOCKER, {
                        "agent": last_agent,
                        "subtask": last_subtask[:120],
                        "blocker": last_result[:300],
                    })
                    if decision == "deny":
                        self.audit.log_run_complete("Stopped by CEO (blocker).", self.spending.tokens_used)
                        log_file = self.audit.save()
                        return {
                            "summary": "Stopped by CEO after worker blocker.",
                            "artifacts": self.station.artifacts,
                            "audit_log": str(log_file),
                        }
                    elif decision != "approve":
                        conversation.append(f"[CEO REDIRECT] {decision}")

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
                        "summary": "Stopped by CEO at spending threshold.",
                        "artifacts": self.station.artifacts,
                        "audit_log": str(log_file),
                    }

            # SUPERVISED mode: checkpoint
            if self.oversight_mode == OversightMode.SUPERVISED and completed:
                last_agent, last_subtask, last_result = completed[-1]
                decision = self._checkpoint(last_agent, last_subtask, last_result)
                if decision == "stop":
                    self.audit.log_run_complete("Stopped by user.", self.spending.tokens_used)
                    log_file = self.audit.save()
                    return {
                        "summary": f"Stopped by user after {self._subtask_count} subtask(s).",
                        "artifacts": self.station.artifacts,
                        "audit_log": str(log_file),
                    }
                if decision != "continue":
                    conversation.append(f"[USER REDIRECT] {decision}")

            # Check spending
            ok, msg = self.spending.check()
            if not ok:
                print(f"\n  {RED}{msg}{RESET}")
                break
        else:
            # Hit iteration limit — synthesize what we have
            summary = f"Completed {len(completed)} subtasks (hit iteration limit)."

        # If no summary yet, ask manager to synthesize
        if not summary or summary.startswith("Completed"):
            print(f"\n{DIM}Manager is synthesizing results...{RESET}", end="", flush=True)
            synth_prompt = f"GOAL: {goal[:500]}\n\n"
            for agent_type, subtask, result in completed:
                synth_prompt += f"--- {agent_type}: {subtask[:100]} ---\n{result[:2000]}\n\n"
            synth_prompt += "Synthesize these results into a clear final summary. What was accomplished? What should the user do next?"

            synthesis = self.manager_llm.call(
                "You are a project manager. Write a clear, actionable summary.",
                synth_prompt,
            )
            self.spending.track(synthesis.input_tokens, synthesis.output_tokens)
            print(f"\r{' '*50}\r", end="")
            summary = synthesis.text
        self.emitter.emit("engine.completed", {"subtasks": len(completed)})
        self.audit.log_run_complete(summary, self.spending.tokens_used)
        log_file = self.audit.save()

        ok, spend_msg = self.spending.check()
        total_time = time.time() - run_start
        if total_time >= 60:
            time_str = f"{int(total_time // 60)}m {int(total_time % 60)}s"
        else:
            time_str = f"{int(total_time)}s"
        print(f"\n{GREEN}Done.{RESET} {DIM}{len(completed)} subtasks in {time_str} | {spend_msg} | Audit: {log_file}{RESET}\n")

        return {
            "summary": summary,
            "artifacts": self.station.artifacts,
            "audit_log": str(log_file),
        }
