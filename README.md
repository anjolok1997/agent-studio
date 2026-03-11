# Agent Studio

A multi-agent AI platform that assembles specialist teams to tackle any project. Pick a template, customize your goal, and let the agents do the work.

Built with the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python).

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/anjolok1997/agent-studio.git
cd agent-studio
```

### 2. Install dependencies

```bash
pip3 install -r requirements.txt
```

### 3. Set up your API key

Create a `.env` file in the project root:

```bash
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > .env
```

Get a key at [console.anthropic.com](https://console.anthropic.com).

> The `.env` file is gitignored — your key stays local and secure.

### 4. Launch

```bash
python3 launch.py
```

You'll see an interactive menu:

```
╔══════════════════════════════════════════════════════╗
║               AGENT STUDIO                           ║
║     Assemble your team. Pick a project. Launch.      ║
╚══════════════════════════════════════════════════════╝

Select a project template:

  1. Code Review
     Review code for quality, security, performance, and maintainability
     Team: code-reviewer, backend-architect, project-manager

  2. Data Pipeline Design
     Design a batch or streaming data pipeline with orchestration and monitoring
     Team: data-engineer, backend-architect, project-manager

  3. Data Quality Framework
     Build a data quality framework with tests, alerts, and data contracts
     Team: data-quality, data-engineer, project-manager

  4. Document Summarizer
     Summarize documents, extract key points, and produce structured digests
     Team: summarizer, project-manager

  5. Research Assistant
     Research a topic, compare approaches, and produce recommendations
     Team: researcher, ai-engineer, project-manager

  0. Custom project
     Write your own goal and pick agents

Select [0-5]:
```

Pick a number, optionally customize the goal, and the agents get to work.

---

## How It Works

```
You → launch.py → pick a template → Engine assigns specialists → QA validates → results
```

**Architecture:**

```
                        ┌─────────────────┐
                        │     Engine       │
                        │  (Manager Agent) │
                        └────────┬────────┘
                                 │ delegates subtasks
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                   ▼
        ┌──────────┐      ┌──────────┐        ┌──────────┐
        │ Station  │      │ Station  │        │ Station  │
        │ Worker A │      │ Worker B │        │ Worker C │
        └─────┬────┘      └─────┬────┘        └─────┬────┘
              │                  │                   │
              ▼                  ▼                   ▼
        ┌──────────────────────────────────────────────┐
        │              Quality Gate                     │
        │     (Reality Checker validates output)        │
        │     Approved → accept | Rejected → retry 3×  │
        └──────────────────────────────────────────────┘
```

1. **Engine** (Manager) breaks your goal into 2-4 subtasks
2. **Station** (Workers) are specialist agents that execute each subtask
3. **Quality Gate** (Reality Checker) validates every output before accepting it
4. If output is rejected, the specialist retries up to 3 times with feedback

---

## Project Structure

```
agent-studio/
├── studio/                  # Core engine
│   ├── __init__.py          # Public API
│   ├── engine.py            # Manager orchestration
│   ├── station.py           # Worker execution
│   ├── quality_gate.py      # QA validation + retry
│   └── events.py            # Event emitter (for external visualizers)
├── agents/                  # Specialist personas (.md files)
│   ├── ai-engineer.md
│   ├── backend-architect.md
│   ├── code-reviewer.md
│   ├── data-engineer.md
│   ├── data-quality.md
│   ├── project-manager.md
│   ├── researcher.md
│   ├── summarizer.md
│   └── reality-checker.md   # QA agent (used by quality gate)
├── templates/               # Project templates (.yaml files)
│   ├── code-review.yaml
│   ├── data-pipeline.yaml
│   ├── data-quality.yaml
│   ├── doc-summarizer.yaml
│   └── research-assistant.yaml
├── archive/                 # Previous versions (for reference)
├── launch.py                # Interactive launcher
├── requirements.txt
├── .env                     # Your API key (gitignored)
└── README.md
```

---

## Templates

Templates are pre-built agent combinations for common tasks. Each one defines a name, description, team of agents, and a default goal.

| Template | Team | Use Case |
|---|---|---|
| **Data Pipeline Design** | data-engineer, backend-architect, project-manager | Design batch/streaming pipelines, DAGs, monitoring |
| **Data Quality Framework** | data-quality, data-engineer, project-manager | dbt tests, data contracts, alerting |
| **Document Summarizer** | summarizer, project-manager | Summarize papers, reports, docs |
| **Research Assistant** | researcher, ai-engineer, project-manager | Compare tools, research topics, produce recommendations |
| **Code Review** | code-reviewer, backend-architect, project-manager | Security, performance, quality review |

### Custom projects

Pick option `0` in the launcher to:
1. Choose your own agents from the available list
2. Write any goal you want

---

## Specialist Agents

| Agent | Best For |
|---|---|
| `ai-engineer` | ML models, LLM pipelines, RAG, embeddings |
| `backend-architect` | APIs, databases, system design, infrastructure |
| `code-reviewer` | Security review, performance, code quality |
| `data-engineer` | Pipelines, Airflow, dbt, Spark, Kafka |
| `data-quality` | dbt tests, data contracts, anomaly detection |
| `project-manager` | Planning, milestones, risk registers |
| `researcher` | Literature review, comparisons, recommendations |
| `summarizer` | Document summaries, key-point extraction |

### Adding your own specialist

Drop a `.md` file in `agents/` — the system discovers it automatically:

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

### Adding a new template

Create a `.yaml` file in `templates/`:

```yaml
name: "Your Template Name"
description: "One-line description"
agents:
  - agent-one
  - agent-two
goal: >
  Default goal for this template. Be specific:
  name the tools, the scale, the expected output.
```

---

## Tips for Better Results

The more specific your goal, the better the output:

| Vague | Specific |
|---|---|
| "Design a pipeline" | "Design an hourly Airflow DAG that pulls from Postgres into Snowflake using incremental loads" |
| "Summarize this paper" | "Summarize the key findings, methodology, and limitations of this ML research paper in 500 words" |
| "Review my code" | "Review this FastAPI service for SQL injection, auth issues, and N+1 query problems" |

---

## Events API (for visualizers)

Agent Studio emits events that external tools can listen to via WebSocket. This is how the [Agentic Kitchen Visualizer](https://github.com/anjolok1997/agentic-kitchen-pycharm) connects.

Events emitted:
- `engine.started` / `engine.completed` / `engine.delegating`
- `worker.started` / `worker.completed` / `worker.tool_called` / `worker.blocked`
- `qa.check_started` / `qa.approved` / `qa.rejected`

To connect a visualizer, pass a WebSocket URL when creating the engine:

```python
from studio import Engine, EventEmitter

emitter = EventEmitter(ws_url="ws://localhost:8765")
engine = Engine(emitter=emitter)
result = engine.run("Your goal here")
```

If no visualizer is connected, events are silently ignored — zero overhead.

---

## Credits

Agent persona patterns inspired by [agency-agents](https://github.com/msitarzewski/agency-agents) by [@msitarzewski](https://github.com/msitarzewski).
