# Architecture

This document explains how Agent Studio is built and how the components work together.

---

## Overview

```
User → launch.py → Material Collection → Engine → Station(s) → Quality Gate → Results
                                            │            │
                                      Permission    MCP Bridge
                                        Guard       (optional)
                                            │
                                       Audit Log
```

Agent Studio follows a **layered architecture** where each layer has a single responsibility:

1. **Launch layer** — user interaction, template selection, material collection
2. **Orchestration layer** — goal decomposition, specialist assignment, synthesis
3. **Execution layer** — worker agents running subtasks with tools
4. **Safety layer** — permissions, spending limits, human approval, audit logging
5. **Integration layer** — MCP bridge for real tool execution, event emitter for visualizers

---

## Core Components

### Engine (`studio/engine.py`)

The Engine is the **manager agent**. It receives a goal and:

1. Breaks it into 2-4 focused subtasks
2. Picks the right specialist for each subtask
3. Delegates via the `delegate_task` tool
4. Optionally asks the human to approve each delegation
5. Collects results and synthesizes a final summary

The Engine controls the overall token budget via `SpendingGuard` and logs everything via `AuditLog`.

```
Engine
├── receives goal + allowed_agents
├── builds manager tools (delegate_task with agent enum)
├── runs manager loop (max 12 iterations)
│   ├── human approval gate (approve / reject / edit)
│   ├── delegates to Station via QualityGate
│   └── tracks spending per API call
└── returns {summary, artifacts, audit_log}
```

### Station (`studio/station.py`)

The Station runs a **single specialist worker** on a subtask. Each worker:

1. Loads its persona from `agents/<type>.md`
2. Has access to tools: `research`, `draft_output`, `flag_blocker` (+ any MCP tools)
3. Runs for up to 6 iterations until `end_turn`
4. Returns its final text output

The Station checks **permissions before every tool call** and routes to MCP if configured.

```
Station._run_tool(name, inputs)
├── PermissionGuard.check() → blocked? return error
├── MCPBridge.has_tool()? → real execution via MCP
└── fallback → simulated tool response
```

### Quality Gate (`studio/quality_gate.py`)

The Quality Gate validates every worker output using the **Reality Checker** agent. It:

1. Sends the subtask + worker output to the checker
2. Gets a verdict: `APPROVED` or `NEEDS WORK`
3. If rejected, the worker retries with feedback (up to 3 attempts)
4. Returns the best output to the Engine

### Agent Personas (`agents/*.md`)

Each specialist is defined by a markdown file with:
- **Identity** — who they are and how they think
- **Mission** — what they're responsible for
- **Expertise** — their skills
- **Deliverables** — what they produce
- **Success Metrics** — how quality is measured
- **Workflow** — their step-by-step approach

The Engine discovers agents automatically by scanning the `agents/` directory.

### Templates (`templates/*.yaml`)

Templates define pre-built project configurations:

```yaml
name: "Template Name"
description: "One-line description"
agents: [agent-one, agent-two]
goal: "Default goal text"
materials:
  - label: "Input name"
    type: text|file
    hint: "What to provide"
    required: true|false
```

The `materials` field guides users on what context to provide for better results.

---

## Safety Layer

### Permission Guard (`studio/permissions.py`)

Classifies every tool call by risk level:

| Risk | Dry-Run Mode (default) | Execute Mode |
|---|---|---|
| **Safe** — read, search, analyze | Allowed | Allowed |
| **Sensitive** — write, create, send | Allowed | Requires approval |
| **Dangerous** — delete, deploy, execute | Blocked | Requires approval |

For MCP tools, risk is inferred from the tool name (e.g., `read_file` → safe, `delete_table` → dangerous) or explicitly set in `mcp_config.yaml`.

### Spending Guard (`studio/permissions.py`)

Hard cap on tokens per run (default: 100,000). Tracks input + output tokens from every API call. Aborts immediately if the cap is exceeded.

### Human Approval (`studio/engine.py`)

Before each subtask delegation, the user sees:
- Which agent will handle it
- What the subtask is
- Options: approve (Y), reject (n), or edit the task (edit)

Skipped subtasks return `[SKIPPED]` to the manager, which adapts accordingly.

### Audit Log (`studio/audit.py`)

Every run creates a JSON log in `logs/` with:
- Run ID and timestamps
- Goal and selected agents
- Each delegation and its agent
- Permission checks (approved/denied)
- Token usage per API call
- Final summary and completion status

---

## Integration Layer

### MCP Bridge (`studio/mcp_bridge.py`)

Connects agent tool calls to real external systems via the [Model Context Protocol](https://modelcontextprotocol.io/).

```
mcp_config.yaml → MCPBridge → discovers tools → registers with PermissionGuard
                                                        │
Station._run_tool() ──► MCPBridge.call_tool() ──► MCP Server ──► real result
```

**How it works:**
1. On startup, reads `mcp_config.yaml` and connects to each server
2. Discovers available tools from each server
3. Registers tool risk levels with the PermissionGuard
4. When a worker calls a tool that MCP provides, the bridge executes it for real
5. If no MCP is configured, everything falls back to simulated tools

**Supported transports:**
- `stdio` — spawns a subprocess (e.g., `npx @modelcontextprotocol/server-filesystem`)
- `sse` — connects to an HTTP server (planned)

### Event Emitter (`studio/events.py`)

Broadcasts events via WebSocket for external visualizers (e.g., the [Agentic Kitchen Visualizer](https://github.com/anjolok1997/agentic-kitchen-pycharm)).

**Events:**

| Event | Source | Data |
|---|---|---|
| `engine.started` | Engine | goal, agents |
| `engine.delegating` | Engine | subtask, agent_type |
| `engine.iteration` | Engine | iteration number |
| `engine.completed` | Engine | iteration count |
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

If no WebSocket client is connected, all `emit()` calls are no-ops with zero overhead.

---

## Data Flow

### Complete request lifecycle

```
1. User runs: python3 launch.py
2. launch.py loads templates, shows menu
3. User picks template, provides materials, customizes goal
4. Materials prepended to goal string
5. Engine created with permissions, spending guard, audit, MCP bridge
6. Engine.run(goal, allowed_agents):
   a. Manager agent breaks goal into subtasks
   b. For each subtask:
      i.   Human approval gate (approve/reject/edit)
      ii.  Station.run(subtask, agent_type)
           - Worker loads persona from agents/<type>.md
           - Worker calls tools (permission-checked, MCP-routed)
           - Worker produces output
      iii. QualityGate.check(subtask, output)
           - APPROVED → accept
           - NEEDS WORK → retry (up to 3×)
      iv.  Result returned to manager
   c. Manager synthesizes final summary
   d. Spending checked after each API call
   e. Audit log saved to logs/
7. launch.py displays summary + artifacts
8. MCP connections cleaned up
```

---

## Technology Stack

| Component | Technology |
|---|---|
| LLM | Claude (Anthropic API) |
| Manager model | claude-sonnet-4-6 |
| Worker model | claude-haiku-4-5-20251001 |
| Language | Python 3.9+ |
| Config | YAML templates + .md agent personas |
| External tools | MCP (Model Context Protocol) |
| Visualization | WebSocket events (consumed by external plugins) |
| Security | PermissionGuard + SpendingGuard + Human approval |
| Logging | JSON audit logs |

---

## Credits

Agent persona patterns inspired by [agency-agents](https://github.com/msitarzewski/agency-agents) by [@msitarzewski](https://github.com/msitarzewski).
