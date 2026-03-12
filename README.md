# Agent Studio

A multi-agent AI platform that assembles specialist teams to tackle any project — from data engineering to education, UX design, business analysis, and more. Pick a template, review the execution plan, and let the agents do the work.

Built with the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python).

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/anjolok1997/agent-studio.git
cd agent-studio
pip3 install -r requirements.txt
```

### 2. Add your API key

```bash
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > .env
```

Get a key at [console.anthropic.com](https://console.anthropic.com). The `.env` file is gitignored — your key stays local and secure.

### 3. Launch

```bash
python3 launch.py
```

You'll see a template menu, provide optional materials, review the execution plan with cost/time estimates, and approve before any expensive work begins.

---

## How It Works

```
1. Pick a template (or create a custom project)
2. Provide materials (documents, context — guided by the template)
3. Review the execution plan (subtasks, cost, time, token estimates)
4. Approve the plan → agents execute
5. After each subtask: checkpoint (continue / stop / redirect)
6. Get final summary + artifacts
```

### Planning Phase

Before any expensive work, a cheap planning call (Haiku) previews the full run:

```
  ══════════════════════════════════════════════════════════
    EXECUTION PLAN
  ══════════════════════════════════════════════════════════

    Subtasks:
      1. [data-engineer] Design the Airflow DAG structure
      2. [backend-architect] Define Snowflake schema and incremental load logic
      3. [project-manager] Create monitoring and alerting plan

    Estimates:
      AI cost:       ~$0.03
      Tokens:        ~26,000 / 100,000 limit
      Time:          ~2-3 minutes
      Models:        Manager=claude-sonnet-4-6, Workers=claude-haiku-4-5-20251001

    Infrastructure detected:
      • Orchestration (airflow)
      • Databases (postgres, snowflake)

  ══════════════════════════════════════════════════════════
    Proceed? [Y/n]:
```

### Checkpoints

After each subtask completes, you see the result and can decide what happens next:

```
  ────────────────────────────────────────────────────────
  Checkpoint — Subtask 1 complete
  Agent:   data-engineer
  Task:    Design the Airflow DAG structure
  Output:  The DAG uses a modular task-group pattern with...
  Tokens used: 8,234 / 100,000
  ────────────────────────────────────────────────────────
  Continue? [Y/n/redirect]:
```

Options: **continue** to the next subtask, **stop** early (keep partial results), or **redirect** with new instructions.

---

## What Can You Do With It?

### Study & Research

> "Create a study guide for distributed systems. Include prerequisites, concept explanations with analogies, and practice questions."

**Template:** Study Guide Builder | **Team:** educator, researcher, summarizer

### Data Engineering

> "Design an hourly Airflow DAG that pulls from Postgres into Snowflake with incremental loads and monitoring."

**Template:** Data Pipeline Design | **Team:** data-engineer, backend-architect, project-manager

### UX Design

> "Audit the onboarding flow of our mobile app. Map the user journey, identify friction points, and check WCAG 2.1 compliance."

**Template:** UX Audit | **Team:** ux-designer, analyst, project-manager

### Business & Analysis

> "Analyze whether we should expand into the European market. Define KPIs, do a SWOT analysis, and give a recommendation."

**Template:** Business Analysis | **Team:** analyst, researcher, project-manager

### Writing & Content

> "Draft a technical blog post explaining how our recommendation engine works, aimed at a non-technical audience."

**Template:** Content Creation | **Team:** writer, researcher, project-manager

### Code Review

> "Review this FastAPI service for SQL injection, auth issues, N+1 queries, and test coverage gaps."

**Template:** Code Review | **Team:** code-reviewer, backend-architect, project-manager

### Custom Projects

Pick option `0` in the launcher to choose your own agents and write any goal.

---

## Model Selection

Choose different models for manager and worker agents based on your needs:

| Model | Speed | Cost | Best For |
|---|---|---|---|
| `haiku` | Fastest | Cheapest | Simple tasks, summaries |
| `sonnet` | Fast | Moderate | Complex reasoning, planning |
| `opus` | Slower | Expensive | Deep analysis, nuanced tasks |

```bash
python3 launch.py --worker-model sonnet      # Use Sonnet for workers (default: haiku)
python3 launch.py --manager-model opus        # Use Opus for manager (default: sonnet)
python3 launch.py --show-models               # Show model details and exit
```

---

## Safety & Controls

### Execution Plan (on by default)

Before spending tokens on workers, review the full plan with cost/time/token estimates. Skip with `--no-plan`.

### Checkpoints (on by default)

After each subtask, review the result and decide: continue, stop, or redirect. Skip with `--no-checkpoints`.

### Spending Cap

Every run is capped at **100,000 tokens** by default. If the limit is hit, the run stops immediately.

```bash
python3 launch.py --token-limit 50000         # Lower spending cap
```

### Material Size Awareness

When you provide large documents, the planner warns you about context window usage:

| Size | Tokens | Action |
|---|---|---|
| Small | < 5,000 | No issues |
| Medium | 5,000–50,000 | No issues |
| Large | 50,000–150,000 | Warning + suggestion to summarize first |
| Very Large | > 150,000 | Warning + suggestion to split into sections |

### Dry-Run Mode (default)

Dangerous tools (database writes, deployments, shell commands) are **blocked by default**. Only enable with `--execute`:

```bash
python3 launch.py --execute --env staging
```

Production targeting requires explicit confirmation:

```bash
python3 launch.py --execute --env prod
# WARNING: Execute mode targeting PRODUCTION.
# Are you sure? [y/N]:
```

### Per-Task Approval (optional)

For extra control, approve each subtask individually before it runs:

```bash
python3 launch.py --approve-each
```

### Audit Log

Every run is logged to `logs/` with full traceability: goal, agents used, delegations, approvals, token usage, and timestamps.

### Tool Risk Classification

| Risk Level | Examples | Dry-Run | Execute Mode |
|---|---|---|---|
| **Safe** | research, analyze | Allowed | Allowed |
| **Sensitive** | draft_output, create_file | Allowed | Requires approval |
| **Dangerous** | run_sql, deploy, shell_exec | Blocked | Requires approval |

---

## All Options

```bash
python3 launch.py                              # Default: plan → approve → execute → checkpoints
python3 launch.py --worker-model sonnet        # Use Sonnet for workers
python3 launch.py --manager-model opus         # Use Opus for manager
python3 launch.py --approve-each               # Approve each subtask individually
python3 launch.py --no-plan                    # Skip planning phase
python3 launch.py --no-checkpoints             # Skip post-subtask checkpoints
python3 launch.py --execute --env dev          # Enable real actions in dev
python3 launch.py --token-limit 50000          # Lower spending cap
python3 launch.py --mcp-config mcp.yaml        # Connect to MCP servers
python3 launch.py --execute --env prod         # Production (requires confirmation)
python3 launch.py --show-models                # Show available models and exit
```

---

## Available Agents

| Agent | Best For |
|---|---|
| `ai-engineer` | ML models, LLM pipelines, RAG, embeddings |
| `analyst` | Data analysis, KPIs, business cases, SWOT |
| `backend-architect` | APIs, databases, system design, infrastructure |
| `code-reviewer` | Security review, performance, code quality |
| `data-engineer` | Pipelines, Airflow, dbt, Spark, Kafka |
| `data-quality` | dbt tests, data contracts, anomaly detection |
| `educator` | Study guides, learning materials, explanations |
| `project-manager` | Planning, milestones, risk registers |
| `researcher` | Literature review, comparisons, recommendations |
| `summarizer` | Document summaries, key-point extraction |
| `ux-designer` | User flows, wireframes, accessibility audits |
| `writer` | Blog posts, docs, proposals, technical writing |

---

## Extend It

### Add a new agent

Drop a `.md` file in `agents/` — discovered automatically:

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

### Add a new template

Create a `.yaml` file in `templates/`:

```yaml
name: "Your Template Name"
description: "One-line description"
agents:
  - agent-one
  - agent-two
goal: >
  Default goal. Be specific: name the tools, scale, and expected output.
materials:
  - label: "Input name"
    type: text        # or "file"
    hint: "What to provide here"
    required: false
```

### Connect to real tools via MCP

Copy and edit the example config:

```bash
cp mcp_config.example.yaml mcp_config.yaml
# Edit with your server details
python3 launch.py --mcp-config mcp_config.yaml --execute
```

### Connect a visualizer

Agent Studio emits events via WebSocket for external tools like the [Agentic Kitchen Visualizer](https://github.com/anjolok1997/agentic-kitchen-pycharm):

```python
from studio import Engine, EventEmitter

emitter = EventEmitter(ws_url="ws://localhost:8765")
engine = Engine(emitter=emitter)
result = engine.run("Your goal here")
```

No visualizer connected? Events are silently ignored — zero overhead.

---

## Tips for Better Results

| Vague | Specific |
|---|---|
| "Design a pipeline" | "Design an hourly Airflow DAG that pulls from Postgres into Snowflake using incremental loads" |
| "Help me study" | "Create a study guide for distributed systems covering CAP theorem, consensus algorithms, and replication" |
| "Review my code" | "Review this FastAPI service for SQL injection, auth issues, and N+1 query problems" |
| "Analyze the market" | "Compare AWS, GCP, and Azure for hosting our ML inference pipeline. Include cost estimates and latency" |

---

## Credits

Agent persona patterns inspired by [agency-agents](https://github.com/msitarzewski/agency-agents) by [@msitarzewski](https://github.com/msitarzewski).
