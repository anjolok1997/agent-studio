# Agent Studio

A multi-agent AI platform that assembles specialist teams to tackle any project — from data engineering to education, UX design, business analysis, and more. Pick a template, customize your goal, and let the agents do the work.

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

Pick a template, optionally customize the goal, approve each step, and get results.

---

## What Can You Do With It?

### Study & Research

> "Create a study guide for distributed systems. Include prerequisites, concept explanations with analogies, and practice questions."

**Template:** Study Guide Builder | **Team:** educator, researcher, summarizer

> "Compare React, Vue, and Svelte for a new frontend project. Produce a recommendation with tradeoffs."

**Template:** Research Assistant | **Team:** researcher, ai-engineer, project-manager

---

### Data Engineering

> "Design an hourly Airflow DAG that pulls from Postgres into Snowflake with incremental loads and monitoring."

**Template:** Data Pipeline Design | **Team:** data-engineer, backend-architect, project-manager

> "Build a data quality framework for our transactions table with dbt tests, alert thresholds, and data contracts."

**Template:** Data Quality Framework | **Team:** data-quality, data-engineer, project-manager

---

### UX Design

> "Audit the onboarding flow of our mobile app. Map the user journey, identify friction points, and check WCAG 2.1 compliance."

**Template:** UX Audit | **Team:** ux-designer, analyst, project-manager

---

### Business & Analysis

> "Analyze whether we should expand into the European market. Define KPIs, do a SWOT analysis, and give a recommendation."

**Template:** Business Analysis | **Team:** analyst, researcher, project-manager

---

### Writing & Content

> "Draft a technical blog post explaining how our recommendation engine works, aimed at a non-technical audience."

**Template:** Content Creation | **Team:** writer, researcher, project-manager

---

### Code Review

> "Review this FastAPI service for SQL injection, auth issues, N+1 queries, and test coverage gaps."

**Template:** Code Review | **Team:** code-reviewer, backend-architect, project-manager

---

### Custom Projects

Pick option `0` in the launcher to choose your own agents and write any goal.

---

## Safety & Controls

Agent Studio includes built-in safeguards to keep you in control.

### Human Approval (on by default)

Before each subtask is delegated, you see what's about to happen and can **approve, reject, or edit** the task:

```
  ────────────────────────────────────────────────────────
  Delegation Request
  Agent:   data-engineer
  Task:    Design the Airflow DAG structure with task dependencies
  ────────────────────────────────────────────────────────
  Approve? [Y/n/edit]:
```

### Spending Cap

Every run is capped at **100,000 tokens** by default. If the limit is hit, the run stops immediately. Override with `--token-limit`:

```bash
python3 launch.py --token-limit 200000
```

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
python3 launch.py                              # Default: dry-run + human approval + 100k cap
python3 launch.py --no-approval                # Skip subtask approval (warns you first)
python3 launch.py --execute --env dev          # Enable real actions in dev
python3 launch.py --token-limit 50000          # Lower spending cap
python3 launch.py --execute --env prod         # Production (requires confirmation)
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
