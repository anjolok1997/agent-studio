# Architecture Overview

This document explains how Agent Studio is built and how the components fit together.

---

## System Flow

```
User --> launch.py --> Material Collection --> Planner --> Engine --> Station(s) --> Quality Gate --> Results
                                                |           |          |
                                             Plan        Permission  MCP Bridge
                                            Review        Guard     (optional)
                                                |           |
                                           Escalation    Audit Log
                                          (CEO mode)
```

## Layers

Agent Studio is organized into six layers, each with a single responsibility:

| Layer | Responsibility | Key Files |
|---|---|---|
| **Launch** | User interaction, template selection, model selection, material collection | `launch.py` |
| **Planning** | Cost/time/token estimation, material size assessment, plan preview | `studio/planner.py` |
| **Orchestration** | Goal decomposition, specialist assignment, escalation, synthesis | `studio/engine.py` |
| **Execution** | Worker agents running subtasks with tools | `studio/station.py` |
| **Safety** | Permissions, spending limits, oversight modes, audit logging | `studio/permissions.py`, `studio/audit.py` |
| **Integration** | MCP bridge for real tools, event emitter for visualizers | `studio/mcp_bridge.py`, `studio/events.py` |

---

## Core Components

### Planner (`studio/planner.py`)

Runs **before** the Engine to give the user a cost/time preview. Uses Haiku (cheapest model) to minimize planning overhead.

What it does:
1. Estimates material token count
2. Assesses material size (small/medium/large/very large) with warnings
3. Detects infrastructure keywords in the goal (AWS, Kafka, etc.) — zero API calls
4. Calls Haiku to break the goal into 2-4 subtasks
5. Displays the plan with cost/time/token estimates
6. User approves or aborts — no expensive tokens spent yet

### Engine (`studio/engine.py`)

The **manager agent**. Receives a goal and orchestrates the full run.

1. Breaks the goal into 2-4 focused subtasks
2. Picks the right specialist for each subtask
3. Delegates via the `delegate_task` tool
4. Handles escalations (CEO mode) or checkpoints (supervised mode)
5. Collects results and synthesizes a final summary

The Engine controls the overall token budget via `SpendingGuard` and logs everything via `AuditLog`.

**Manager loop**: runs up to 12 iterations. Each iteration is one Claude API call where the manager can delegate one or more subtasks. After all delegations return, the manager synthesizes a final summary.

### Station (`studio/station.py`)

Runs a **single specialist worker** on a subtask.

1. Loads the agent persona via `AgentLoader` (library or local)
2. Gives the worker access to tools: `research`, `draft_output`, `flag_blocker` + any MCP tools
3. Runs for up to 6 iterations until `end_turn`
4. Returns the worker's final text output

Every tool call is permission-checked before execution. If MCP is configured, matching tools route to real systems; otherwise, tools return simulated responses.

### Quality Gate (`studio/quality_gate.py`)

Validates every worker output using the **Reality Checker** agent.

1. Sends the subtask + worker output to the checker
2. Gets a verdict: `APPROVED` or `NEEDS WORK`
3. If rejected, the worker retries with feedback (up to 3 attempts)
4. Returns the best output to the Engine

This is automatic QA — no human involvement.

### Agent Loader (`studio/agent_loader.py`)

Unified agent discovery from two sources:

1. **Library** (`lib/agency-agents/`) — 147 agents across 13 categories from the [agency-agents](https://github.com/msitarzewski/agency-agents) repository
2. **Local** (`agents/`) — User's custom agents, override library agents with the same ID

The loader parses YAML frontmatter (name, description, emoji) for display in the menu, and returns the full markdown content as the system prompt.

See [Agent System](agents.md) for details.

---

## Data Flow

### Complete request lifecycle

```
 1. User runs: python3 launch.py
 2. launch.py loads templates and agent library, shows menu
 3. User picks template (or custom project), provides materials, customizes goal
 4. Materials prepended to goal string
 5. Planning phase (unless --no-plan):
    a. Planner assesses material size and detects infrastructure
    b. Planner calls Haiku to break goal into subtasks
    c. Displays plan with cost/time/token estimates
    d. User approves or aborts
 6. Engine created with permissions, spending guard, audit, oversight mode
 7. Engine.run(goal, allowed_agents):
    a. Manager agent breaks goal into subtasks
    b. For each subtask:
       i.   Station.run(subtask, agent_type)
            - Worker loads persona from AgentLoader
            - Worker calls tools (permission-checked, MCP-routed)
            - Worker produces output
       ii.  QualityGate.check(subtask, output)
            - APPROVED -> accept
            - NEEDS WORK -> retry (up to 3x)
       iii. CEO mode: check for escalation triggers
            - Worker blocker? -> pause, show blocker, wait for CEO
            - Spending threshold? -> pause, show usage, wait for CEO
       iv.  SUPERVISED mode: checkpoint
            - User reviews result (continue / stop / redirect)
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
| LLM | Claude (via CLI subscription or Anthropic API) |
| Planner model | claude-haiku-4-5-20251001 (cheapest) |
| Manager model | claude-sonnet-4-6 (configurable) |
| Worker model | claude-haiku-4-5-20251001 (configurable) |
| Language | Python 3.9+ |
| Agent library | [agency-agents](https://github.com/msitarzewski/agency-agents) (MIT) |
| Config | YAML templates + markdown agent personas |
| External tools | MCP (Model Context Protocol) |
| Visualization | WebSocket events |
| Security | PermissionGuard + SpendingGuard + CEO/Supervised modes |
| Logging | JSON audit logs |

---

## File Structure

```
agent-studio/
  launch.py                    # CLI entry point
  requirements.txt             # Python dependencies
  mcp_config.example.yaml      # MCP server config example
  agents/                      # Local agent personas (user overrides)
    backend-architect.md
    ...
  lib/
    agency-agents/             # Agent library (git submodule)
      engineering/
      design/
      marketing/
      ...
  studio/                      # Core framework
    __init__.py
    engine.py                  # Manager orchestration
    station.py                 # Worker execution
    agent_loader.py            # Library + local agent discovery
    cli_client.py              # Claude CLI wrapper for subscription mode
    quality_gate.py            # Output validation
    planner.py                 # Pre-execution planning
    permissions.py             # Risk classification, oversight modes
    audit.py                   # JSON audit logging
    events.py                  # WebSocket event emitter
    mcp_bridge.py              # MCP tool integration
  templates/                   # Project templates (YAML)
  docs/                        # Technical documentation
  logs/                        # Audit logs (auto-created)
```
