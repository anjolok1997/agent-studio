# Safety and Permissions

Agent Studio has multiple safety layers that work together to prevent unintended actions, control costs, and maintain audit trails.

---

## Execution Modes

| Mode | Flag | Behavior |
|---|---|---|
| **Dry-Run** (default) | _(none)_ | Dangerous tools blocked. Sensitive tools produce in-memory artifacts only. |
| **Execute** | `--execute` | Real actions via MCP. Dangerous tools require CEO approval. |

Dry-run is the default because it's safe to experiment with — nothing leaves the system.

```bash
python3 launch.py                       # Dry-run: no real actions
python3 launch.py --execute --env dev   # Real actions in dev
python3 launch.py --execute --env prod  # Real actions in production (extra warnings)
```

---

## Tool Risk Classification

Every tool call is classified by risk before execution:

| Risk Level | Examples | Dry-Run | Execute (CEO Mode) |
|---|---|---|---|
| **Safe** | `research`, `read_file`, `flag_blocker` | Allowed | Allowed |
| **Sensitive** | `draft_output`, `write_file`, `send_message`, `call_api` | Allowed | Auto-approved |
| **Dangerous** | `run_sql`, `run_shell`, `deploy`, `terraform_apply` | Blocked | CEO approval required |

### Risk classification for MCP tools

When agents use tools from MCP servers, risk is inferred from the tool name:
- Names containing `read`, `get`, `list`, `search` -> Safe
- Names containing `write`, `create`, `send`, `update` -> Sensitive
- Names containing `delete`, `drop`, `deploy`, `execute`, `run` -> Dangerous

You can override risk levels in `mcp_config.yaml`.

### Production escalation

When `--env prod` is set, **any non-Safe tool** triggers a CEO escalation in CEO mode (or requires approval in supervised mode). This applies even to Sensitive tools like `write_file` — because writing in production is different from writing in dev.

---

## Spending Guard

Hard cap on tokens per run. Tracks input + output tokens from every API call.

| Parameter | Default | Flag |
|---|---|---|
| Max tokens | 100,000 | `--token-limit 50000` |
| Threshold alert | 80% | _(not configurable)_ |

### How it works

1. Every API call's token usage is tracked
2. At 80% of the limit (CEO mode only), execution pauses and the CEO is asked whether to continue
3. At 100%, execution stops immediately regardless of mode

The threshold alert fires **once** — if you approve, it won't ask again until the hard cap.

---

## Audit Log

Every run creates a JSON log in `logs/` with:

- Run ID and timestamps
- Goal and selected agents
- Each delegation (subtask + agent)
- Permission checks (approved/denied)
- Escalation events (reason + CEO decision)
- Token usage per API call
- Final summary and completion status

### Log format

```json
{
  "run_id": "run_1711835400",
  "started": "2024-03-31T10:30:00",
  "completed": "2024-03-31T10:32:15",
  "entries": [
    {
      "run_id": "run_1711835400",
      "timestamp": "2024-03-31T10:30:01",
      "event": "run.started",
      "data": {"goal": "...", "agents": [...], "mode": "dry-run"}
    },
    {
      "event": "task.delegated",
      "data": {"subtask": "...", "agent_type": "engineering-sre"}
    },
    {
      "event": "escalation",
      "data": {"reason": "dangerous_tool", "context": {...}, "decision": "approved"}
    },
    {
      "event": "tokens.used",
      "data": {"input": 1234, "output": 567, "model": "claude-sonnet-4-6"}
    }
  ]
}
```

---

## Human Control Summary

| Control | CEO Mode | Supervised Mode |
|---|---|---|
| Execution plan review | Before run (optional) | Before run (optional) |
| Delegation approval | Automatic | Per-subtask |
| Post-subtask review | None | Checkpoint (continue/stop/redirect) |
| Dangerous tool calls | CEO escalation | Approval prompt |
| Production actions | CEO escalation | Approval prompt |
| Spending alerts | Escalation at 80% | No alert (hard cap only) |
| Worker blockers | CEO escalation | Visible at checkpoint |
| Quality validation | Automatic (QA agent) | Automatic (QA agent) |
| Audit trail | Always | Always |

---

## PermissionGuard API

```python
from studio.permissions import PermissionGuard, ExecutionMode, OversightMode

# CEO mode (default)
guard = PermissionGuard(
    mode=ExecutionMode.EXECUTE,
    environment="prod",
    oversight=OversightMode.CEO,
)

allowed, reason = guard.check("deploy", {"service": "api"})
# -> Pauses, shows escalation prompt, returns (True/False, reason)
```

## SpendingGuard API

```python
from studio.permissions import SpendingGuard

guard = SpendingGuard(max_tokens=100_000, threshold=0.8)
guard.track(input_tokens=5000, output_tokens=2000)

ok, message = guard.check()           # (True, "7,000 / 100,000 tokens used")
should_alert = guard.should_escalate() # True when >= 80%, fires once
```
