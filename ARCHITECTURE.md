# Architecture

This document explains how Agent Studio is built and how the components work together.

---

## Overview

```
User → launch.py → Material Collection → Planner → Engine → Station(s) → Quality Gate → Results
                                            │          │          │
                                         Plan       Permission  MCP Bridge
                                        Review       Guard     (optional)
                                            │          │
                                        Checkpoints  Audit Log
```

Agent Studio follows a **layered architecture** where each layer has a single responsibility:

1. **Launch layer** — user interaction, template selection, model selection, material collection
2. **Planning layer** — cost/time/token estimation, material size assessment, plan preview
3. **Orchestration layer** — goal decomposition, specialist assignment, checkpoints, synthesis
4. **Execution layer** — worker agents running subtasks with tools
5. **Safety layer** — permissions, spending limits, human approval, audit logging
6. **Integration layer** — MCP bridge for real tool execution, event emitter for visualizers

---

## Core Components

### Planner (`studio/planner.py`)

The Planner runs **before** the Engine to give the user a cost/time preview. It uses Haiku (cheapest model) to minimize planning overhead.

```
Planner
├── _estimate_material_tokens(goal) → token count for embedded materials
├── _assess_material_size(tokens, model) → size label + warnings + recommendations
├── _detect_infra(goal) → infrastructure keywords (AWS, Kafka, etc.) — zero API calls
├── create_plan(goal, agents, worker_model, manager_model):
│   ├── strips material content from planning prompt (sends token count only)
│   ├── asks Haiku to break goal into 2-4 subtasks
│   ├── parses SUBTASK: [agent-type] Description format
│   └── returns {subtasks, estimates, infrastructure, material_assessment}
└── display_plan(plan) → formatted preview, user approves or aborts
```

**Material size assessment:**

| Size | Tokens | Behavior |
|---|---|---|
| Small | < 5,000 | No issues |
| Medium | 5,000–50,000 | No issues |
| Large | 50,000–150,000 | Warning + summarize-first suggestion |
| Very Large | > 150,000 | Warning + split-document suggestion |

If material exceeds 60% of the context window, a capacity warning is shown.

**Infrastructure detection** scans the goal text for keywords across categories: AWS, GCP, Azure, Databases, Streaming, Orchestration, Containers, CI/CD, Monitoring. Zero API calls — pure string matching.

### Engine (`studio/engine.py`)

The Engine is the **manager agent**. It receives a goal and:

1. Breaks it into 2-4 focused subtasks
2. Picks the right specialist for each subtask
3. Delegates via the `delegate_task` tool
4. After each subtask: runs a **checkpoint** (continue / stop / redirect)
5. Collects results and synthesizes a final summary

The Engine controls the overall token budget via `SpendingGuard` and logs everything via `AuditLog`.

```
Engine
├── receives goal + allowed_agents
├── builds manager tools (delegate_task with agent enum)
├── runs manager loop (max 12 iterations)
│   ├── optional per-task approval gate (--approve-each)
│   ├── delegates to Station via QualityGate
│   ├── checkpoint: user reviews result (continue / stop / redirect)
│   └── tracks spending per API call
└── returns {summary, artifacts, audit_log}
```

**Checkpoint flow:** After each subtask completes, the user sees the agent, task, output preview, and token usage. They can:
- **Continue** — proceed to the next subtask
- **Stop** — halt execution, keep partial results
- **Redirect** — inject new instructions for remaining tasks

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

### Human Control Flow

Agent Studio provides three layers of human control:

1. **Plan approval** (default) — review the full execution plan before any expensive work
2. **Checkpoints** (default) — review each subtask result, stop or redirect at any point
3. **Per-task approval** (optional, `--approve-each`) — approve each delegation before it runs

```
Plan approval → [Subtask 1] → Checkpoint → [Subtask 2] → Checkpoint → ... → Summary
                     │                          │
               (optional per-task          (continue /
                approval gate)              stop / redirect)
```

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

If no WebSocket client is connected, all `emit()` calls are no-ops with zero overhead.

---

## Data Flow

### Complete request lifecycle

```
1. User runs: python3 launch.py
2. launch.py loads templates, shows menu
3. User picks template, provides materials, customizes goal
4. Materials prepended to goal string
5. Planning phase (unless --no-plan or --approve-each):
   a. Planner assesses material size and detects infrastructure
   b. Planner calls Haiku to break goal into subtasks
   c. Displays plan with cost/time/token estimates
   d. User approves or aborts (no expensive tokens spent yet)
6. Engine created with permissions, spending guard, audit, MCP bridge
7. Engine.run(goal, allowed_agents):
   a. Manager agent breaks goal into subtasks
   b. For each subtask:
      i.   Optional per-task approval gate (--approve-each only)
      ii.  Station.run(subtask, agent_type)
           - Worker loads persona from agents/<type>.md
           - Worker calls tools (permission-checked, MCP-routed)
           - Worker produces output
      iii. QualityGate.check(subtask, output)
           - APPROVED → accept
           - NEEDS WORK → retry (up to 3×)
      iv.  Checkpoint: user reviews result
           - continue → next subtask
           - stop → return partial results
           - redirect → inject new instructions
      v.   Result returned to manager
   c. Manager synthesizes final summary
   d. Spending checked after each API call
   e. Audit log saved to logs/
8. launch.py displays summary + artifacts
9. MCP connections cleaned up
```

---

## Technology Stack

| Component | Technology |
|---|---|
| LLM | Claude (Anthropic API) |
| Planner model | claude-haiku-4-5-20251001 (cheapest) |
| Manager model | claude-sonnet-4-6 (configurable) |
| Worker model | claude-haiku-4-5-20251001 (configurable) |
| Language | Python 3.9+ |
| Config | YAML templates + .md agent personas |
| External tools | MCP (Model Context Protocol) |
| Visualization | WebSocket events (consumed by external plugins) |
| Security | PermissionGuard + SpendingGuard + Plan approval + Checkpoints |
| Logging | JSON audit logs |

---

## Credits

Agent persona patterns inspired by [agency-agents](https://github.com/msitarzewski/agency-agents) by [@msitarzewski](https://github.com/msitarzewski).
