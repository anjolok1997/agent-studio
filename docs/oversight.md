# Oversight Modes

Agent Studio has two oversight modes that control how much the human is involved during execution.

---

## CEO Mode (default)

The human is the CEO. Agents run autonomously and only escalate when something genuinely requires human judgment.

```bash
python3 launch.py                    # CEO mode is the default
python3 launch.py --execute --env prod  # Escalates on production actions
```

### What runs without interruption

- Task decomposition (manager picks subtasks and agents)
- All SAFE tool calls (research, analysis)
- All SENSITIVE tool calls in non-production environments (drafting, file creation)
- Quality gate validation and retries
- Manager synthesis

### Escalation triggers

The agent pauses and waits for CEO approval when:

| Trigger | When | What you see |
|---|---|---|
| **Dangerous tool** | `run_sql`, `deploy`, `shell_exec`, `terraform_apply` | Tool name, inputs, risk level |
| **Production target** | Any non-SAFE tool when `--env prod` | Tool name + production warning |
| **Spending threshold** | Token usage crosses 80% of budget | Tokens used vs limit |
| **Worker blocker** | Agent uses `flag_blocker` tool | Blocker reason from the agent |

### Escalation prompt

When an escalation fires, you see:

```
  ============================================================
  ESCALATION -- CEO APPROVAL REQUIRED
  Reason: DANGEROUS TOOL
  ============================================================
  Tool:        deploy
  Risk:        dangerous
  Environment: staging
  Inputs:      {"service": "api", "version": "2.1.0"}
  ============================================================
  [Y] Approve   [n] Deny   [m] Modify

  Decision:
```

Options:
- **Approve** (Y or Enter) — proceed with the action
- **Deny** (n) — block the action, agent continues without it
- **Modify** (m) — provide alternative instructions

### Spending threshold

Fires **once** when 80% of the token budget is used. This gives you a chance to stop before hitting the hard cap. If you approve, execution continues until the hard cap or completion.

---

## Supervised Mode

The legacy mode for users who want full visibility and control at every step.

```bash
python3 launch.py --supervised
```

### What happens in supervised mode

1. **Per-delegation approval** — Before each subtask is assigned, you see the task and agent, and can approve, reject, or edit.
2. **Post-subtask checkpoints** — After each subtask completes, you see the output and can continue, stop, or redirect.
3. **Tool-level approval** — SENSITIVE and DANGEROUS tools both require approval in execute mode (same as the old behavior).

### Checkpoint prompt

```
  --------------------------------------------------------
  Checkpoint -- Subtask 1 complete
  Agent:   data-engineer
  Task:    Design the Airflow DAG structure
  Output:  The DAG uses a modular task-group pattern with...
  Tokens used: 8,234 / 100,000
  --------------------------------------------------------
  Continue? [Y/n/redirect]:
```

Options:
- **Continue** (Y or Enter) — proceed to next subtask
- **Stop** (n) — halt execution, keep partial results
- **Redirect** (r) — inject new instructions for remaining tasks

---

## Comparison

| Feature | CEO Mode | Supervised Mode |
|---|---|---|
| Task delegation | Automatic | Requires approval |
| Post-subtask checkpoints | None | After every subtask |
| SAFE tools | Auto-approved | Auto-approved |
| SENSITIVE tools (non-prod) | Auto-approved | Requires approval |
| DANGEROUS tools | Escalation | Requires approval |
| Production actions | Escalation | Requires approval |
| Spending threshold | Escalation at 80% | No threshold alert |
| Worker blockers | Escalation | Shown at checkpoint |
| Quality gate | Automatic | Automatic |
| Plan approval | Optional (`--no-plan`) | Optional (`--no-plan`) |

---

## Implementation

Oversight mode is set by `OversightMode` enum in `studio/permissions.py` and threaded through:

- `PermissionGuard` — controls which tool calls need approval
- `Engine` — controls whether checkpoints and delegation approval are active
- `launch.py` — selects mode based on `--supervised` flag

The `EscalationReason` enum tracks why an escalation was triggered:

```python
class EscalationReason(Enum):
    DANGEROUS_TOOL = "dangerous_tool"
    PRODUCTION_TARGET = "production_target"
    SPENDING_THRESHOLD = "spending_threshold"
    WORKER_BLOCKER = "worker_blocker"
```

All escalation events are logged to the audit trail with the reason, context, and CEO decision.
