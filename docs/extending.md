# Extending Agent Studio

How to add agents, templates, connect real tools, and attach visualizers.

---

## Add a New Agent

Drop a `.md` file in `agents/`. It's discovered automatically on next launch.

```markdown
# Your Specialist Name

## Identity
Who this agent is and how they think.

## Mission
What they deliver.

## Expertise
- Skill 1
- Skill 2

## Deliverables
- Output 1
- Output 2

## Success Metrics
- How you know the output is good

## Workflow
1. Step one
2. Step two
```

Optional: add YAML frontmatter for a richer menu display:

```markdown
---
name: Your Specialist Name
description: One-line description of what this agent does
emoji: <your emoji>
---

# Your Specialist Name
...
```

### Override a library agent

Copy the library agent to `agents/` with the same filename, then edit:

```bash
cp lib/agency-agents/engineering/engineering-sre.md agents/engineering-sre.md
```

Your local version takes priority.

---

## Add a New Template

Create a `.yaml` file in `templates/`:

```yaml
name: "Your Template Name"
description: "One-line description shown in the menu"
agents:
  - agent-id-one
  - agent-id-two
  - agent-id-three
goal: >
  Default goal. Be specific: name the tools, scale, and expected output.
materials:
  - label: "Input name"
    type: text        # or "file"
    hint: "What to provide here"
    required: false
```

Agent IDs can be from the library (`engineering-backend-architect`) or local (`backend-architect`).

### Materials

Materials are inputs the user provides before the run. They're prepended to the goal text.

| Field | Description |
|---|---|
| `label` | Display name shown to the user |
| `type` | `text` (inline input) or `file` (file path, contents loaded) |
| `hint` | Helper text explaining what to provide |
| `required` | If true, user must provide a value |

---

## Connect Real Tools via MCP

The [Model Context Protocol](https://modelcontextprotocol.io/) connects agent tool calls to real external systems.

### Setup

1. Copy and edit the example config:

```bash
cp mcp_config.example.yaml mcp_config.yaml
```

2. Configure your servers:

```yaml
servers:
  - name: filesystem
    transport: stdio
    command: npx
    args: ["@modelcontextprotocol/server-filesystem", "/path/to/workspace"]

  - name: database
    transport: stdio
    command: npx
    args: ["@modelcontextprotocol/server-postgres", "postgresql://..."]
    risk_overrides:
      read_query: safe
      write_query: dangerous
```

3. Launch with MCP:

```bash
python3 launch.py --mcp-config mcp_config.yaml --execute
```

### How it works

1. On startup, the MCP bridge connects to each server and discovers available tools
2. Tools are registered with the PermissionGuard (risk inferred from tool name or set via `risk_overrides`)
3. Workers see MCP tools alongside built-in tools
4. When a worker calls an MCP tool, the bridge routes the call to the real server
5. If no MCP is configured, everything falls back to simulated tool responses

### Supported transports

| Transport | Description |
|---|---|
| `stdio` | Spawns a subprocess (most common) |
| `sse` | Connects to an HTTP server (planned) |

---

## Connect a Visualizer

Agent Studio emits events via WebSocket for external visualization tools.

```python
from studio import Engine, EventEmitter

emitter = EventEmitter(ws_url="ws://localhost:8765")
engine = Engine(emitter=emitter)
result = engine.run("Your goal here")
```

No visualizer connected? All `emit()` calls are silently ignored — zero overhead.

### Available events

| Event | Source | Data |
|---|---|---|
| `engine.started` | Engine | goal, agents |
| `engine.delegating` | Engine | subtask, agent_type |
| `engine.escalation` | Engine | reason, context |
| `engine.iteration` | Engine | iteration number |
| `engine.completed` | Engine | iteration count |
| `planner.started` | Planner | goal |
| `planner.completed` | Planner | subtask count |
| `worker.started` | Station | agent, subtask, attempt |
| `worker.tool_called` | Station | agent, tool, details |
| `worker.blocked` | Station | agent, reason |
| `worker.tool_blocked` | Station | agent, tool, reason |
| `worker.completed` | Station | agent, chars |
| `qa.check_started` | QualityGate | subtask |
| `qa.approved` | QualityGate | verdict |
| `qa.rejected` | QualityGate | verdict |
| `mcp.connected` | MCPBridge | server, tool count |
| `mcp.tool_called` | MCPBridge | server, tool, agent |
| `mcp.tool_error` | MCPBridge | server, tool, error |

### Compatible visualizers

- [Agentic Kitchen Visualizer](https://github.com/anjolok1997/agentic-kitchen-pycharm) — PyCharm/IntelliJ plugin

---

## Programmatic Usage

Use Agent Studio as a library in your own code:

```python
from anthropic import Anthropic
from studio import Engine, PermissionGuard, SpendingGuard, AuditLog, AgentLoader
from studio.permissions import ExecutionMode, OversightMode

client = Anthropic()
permissions = PermissionGuard(
    mode=ExecutionMode.DRY_RUN,
    oversight=OversightMode.CEO,
)

engine = Engine(
    client=client,
    manager_model="claude-sonnet-4-6",
    worker_model="claude-haiku-4-5-20251001",
    permissions=permissions,
    spending_guard=SpendingGuard(max_tokens=50_000),
    audit=AuditLog(),
    oversight_mode=OversightMode.CEO,
)

result = engine.run(
    goal="Design an hourly Airflow DAG for Postgres to Snowflake",
    allowed_agents=["data-engineer", "backend-architect"],
)

print(result["summary"])
print(result["artifacts"])
print(result["audit_log"])
```

### Custom agent loader

```python
from studio.agent_loader import AgentLoader
from pathlib import Path

loader = AgentLoader(
    local_dir=Path("./my-agents"),
    library_dir=Path("./lib/agency-agents"),
)

# Use with station
from studio import Station
station = Station(client, agent_loader=loader)
```

---

## Update the Agent Library

The agency-agents library is a git submodule. To get the latest agents:

```bash
git submodule update --remote lib/agency-agents
```

To pin a specific version:

```bash
cd lib/agency-agents
git checkout <commit-or-tag>
cd ../..
git add lib/agency-agents
git commit -m "Pin agency-agents to <version>"
```
