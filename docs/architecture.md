# Architecture Overview

This document explains how Agent Studio is built and how the components fit together.

---

## System Flow

```
User --> launch.py --> Material Collection --> Briefing --> Engine --> Station(s) --> User Spot-Check --> Results
                                                |            |          |               |
                                            Manager       Permission  MCP Bridge     Approve /
                                           1-on-1 chat     Guard    (Docker sandbox) Feedback /
                                                |            |                        Skip
                                           Escalation    Audit Log
                                          (CEO mode)
```

## Layers

Agent Studio is organized into six layers, each with a single responsibility:

| Layer | Responsibility | Key Files |
|---|---|---|
| **Launch** | User interaction, template selection, model selection, material collection | `launch.py` |
| **Briefing** | Interactive manager conversation before execution | `studio/briefing.py` |
| **Planning** | Cost/time/token estimation (legacy, via `--classic-plan`) | `studio/planner.py` |
| **Orchestration** | Goal decomposition, parallel/sequential delegation, escalation, synthesis | `studio/engine.py` |
| **Execution** | Worker agents running subtasks with MCP tools | `studio/station.py` |
| **Quality** | User spot-check of each worker's output (approve/feedback/skip) | `studio/quality_gate.py` |
| **Safety** | Permissions, spending limits, oversight modes, audit logging | `studio/permissions.py`, `studio/audit.py` |
| **Integration** | MCP bridge (Docker sandboxed), event emitter for visualizers | `studio/mcp_bridge.py`, `studio/mcp_sandbox.py`, `studio/events.py` |

---

## Core Components

### Briefing (`studio/briefing.py`)

Runs **before** the Engine. The **briefing manager** agent (a dedicated specialist loaded from `agents/briefing-manager.md`) has a 1-on-1 conversation with the user to align on approach.

1. Manager analyzes the goal and proposes an approach (which specialists, in what order)
2. User can ask questions, refine scope, adjust priorities
3. When aligned, user types `go` to start execution
4. Briefing transcript is passed to the Engine as context

Uses the manager model (Sonnet) — smarter than the legacy Haiku planner. The old plan + Y/n flow is available via `--classic-plan`.

### Planner (`studio/planner.py`) — Legacy

The original planning phase, now available via `--classic-plan`. Uses Haiku for a quick cost/time preview with a simple approve/reject prompt.

### Engine (`studio/engine.py`)

The **manager agent**. Receives a goal (plus optional briefing context) and orchestrates the full run.

1. Manager decides what to delegate next
2. Uses `PARALLEL:` for independent tasks (run simultaneously) or `DELEGATE:` for sequential tasks
3. Workers execute via `ThreadPoolExecutor` for parallel batches
4. Handles escalations (CEO mode) or checkpoints (supervised mode)
5. Collects results and synthesizes a final summary

The Engine controls the overall token budget via `SpendingGuard` and logs everything via `AuditLog`.

**Manager loop**: runs up to 8 iterations. Each iteration, the manager can delegate one sequential task or a batch of parallel tasks.

### Station (`studio/station.py`)

Runs a **single specialist worker** on a subtask.

1. Loads the agent persona via `AgentLoader` (library or local)
2. If MCP tools are available: runs a tool-calling loop (API provider) or passes `--mcp-config` to Claude CLI
3. Returns the worker's final text output

Every MCP tool call is permission-checked and routed through the Docker sandbox when configured.

### Quality Gate (`studio/quality_gate.py`)

**User spot-check** — shows a preview of each worker's output and lets the user decide.

1. Displays a compact preview (first and last few hundred chars)
2. User chooses: **approve** (Enter), **feedback & retry** (f), or **skip** (s)
3. If feedback given, the worker retries with that guidance (up to 2 attempts)
4. Returns the accepted output to the Engine

This replaced the old LLM-checking-LLM approach, which had the same hallucination blind spots as the workers themselves.

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
 5. Briefing phase (unless --no-plan):
    a. Briefing manager loads from agents/briefing-manager.md
    b. Manager discusses approach with user (multi-turn conversation)
    c. User types 'go' to proceed, 'quit' to abort
    d. Briefing transcript saved as context for engine
    (Legacy: --classic-plan uses Haiku planner with Y/n instead)
 6. Engine created with permissions, spending guard, audit, oversight mode
 7. Engine.run(goal, allowed_agents, briefing_context):
    a. Manager reads briefing context + goal
    b. For each iteration:
       - Manager responds with DELEGATE: (sequential) or PARALLEL: (concurrent)
       - Parallel tasks: run simultaneously via ThreadPoolExecutor
       - Sequential tasks: run one at a time
       i.   Station.run(subtask, agent_type)
            - Worker loads persona from AgentLoader
            - Worker calls MCP tools if available (Docker sandboxed)
            - Worker produces output
       ii.  QualityGate: user spot-check
            - User sees preview, approves / gives feedback / skips
            - If feedback: worker retries (up to 2x)
       iii. CEO mode: check for escalation triggers
       iv.  SUPERVISED mode: checkpoint
       v.   Result(s) returned to manager
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
| LLM | Claude (via CLI login or Anthropic API key) |
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
    engine.py                  # Manager orchestration (parallel + sequential)
    station.py                 # Worker execution (with MCP tool-calling loop)
    briefing.py                # Interactive manager briefing before execution
    agent_loader.py            # Library + local agent discovery
    llm.py                     # Unified LLM interface (CLI + API)
    scheduler.py               # Recurring task scheduler
    quality_gate.py            # User spot-check (approve/feedback/skip)
    planner.py                 # Legacy planning (--classic-plan)
    permissions.py             # Risk classification, oversight modes
    audit.py                   # JSON audit logging
    events.py                  # WebSocket event emitter
    mcp_bridge.py              # MCP tool integration
    mcp_cli.py                 # Interactive MCP server setup (studio mcp add)
    mcp_sandbox.py             # Docker sandbox for MCP servers
  docker/
    mcp/
      Dockerfile.base          # Base image for sandboxed MCP servers
  agents/                      # Local agent personas (user overrides)
    briefing-manager.md        # Specialist agent for pre-execution briefing
    ...
  templates/                   # Project templates (YAML)
  examples/
    mcp/                       # Ready-to-use MCP configs (version-pinned)
      filesystem.yaml
      github.yaml
      postgres.yaml
      slack.yaml
      custom.yaml
  schedules/                   # Recurring task configs (YAML, auto-created)
  logs/                        # Audit logs (auto-created)
  docs/                        # Technical documentation
```
