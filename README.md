# Workflow Agent

A hands-on learning project for building AI agents with the [Anthropic Python SDK](https://github.com/anthropics/anthropic-sdk-python). Agents use Claude to manage tasks, delegate work to specialists, and validate outputs automatically.

---

## Setup

**1. Install dependencies**
```bash
pip3 install anthropic
```

**2. Set your API key**
```bash
export ANTHROPIC_API_KEY='sk-ant-...'
```

Get a key at [console.anthropic.com](https://console.anthropic.com).

---

## The Three Files

| File | What it does |
|---|---|
| `workflow_agent.py` | Single agent that manages a task list |
| `multi_agent.py` | Manager delegates subtasks to Worker agents |
| `multi_agent_v2.py` | Manager + specialist agents + QA quality gate |

Start with `workflow_agent.py`, then graduate to `multi_agent_v2.py`.

---

## workflow_agent.py — Single Agent

The simplest entry point. Give it a goal; it breaks the goal into tasks, tracks status, and adds notes.

```bash
python3 workflow_agent.py
```

**Tools the agent can use:**

| Tool | What it does |
|---|---|
| `create_task` | Add a task to the list |
| `list_tasks` | See all tasks and their status |
| `update_task_status` | Mark a task todo / in_progress / done |
| `add_note` | Attach a note to a task |
| `summarize_progress` | Count tasks by status |

### Scenarios

**Plan a product launch**
```
Enter your workflow goal: Plan the launch of a new mobile app feature —
write the spec, build it, test it, then deploy.
```
The agent will create tasks for each phase, mark them in_progress, add notes about
what each step involves, and finish with a progress summary.

---

**Prepare for a job interview**
```
Enter your workflow goal: Help me prepare for a software engineering interview
next week. I need to review algorithms, practice system design, and do mock questions.
```
The agent breaks this into structured tasks (e.g. "Review sorting algorithms",
"Practice LeetCode mediums", "Mock system design: design Twitter") with notes on
what to focus on.

---

**Manage a writing project**
```
Enter your workflow goal: I'm writing a technical blog post about vector databases.
Help me plan the research, outline, draft, and publish steps.
```

---

## multi_agent_v2.py — Specialist Agents + QA Gate

The most powerful version. A Manager agent breaks your goal into subtasks and assigns each to the right specialist. A Reality Checker QA agent validates every output before accepting it (retries up to 3×).

```bash
python3 multi_agent_v2.py
```

**Available specialists** (add more by dropping a `.md` in `agents/`):

| Agent | Best for |
|---|---|
| `ai-engineer` | ML models, LLM pipelines, embeddings, AI features |
| `backend-architect` | APIs, databases, system design, infrastructure |
| `project-manager` | Planning, task sequencing, risk identification |

### Scenarios

**Design an AI-powered product**
```
Enter your goal: Design a smart email assistant that reads my inbox,
summarizes threads, and drafts replies in my tone.
```
- `project-manager` → breaks down the project phases and milestones
- `ai-engineer` → designs the LLM pipeline for summarization and tone matching
- `backend-architect` → specifies the API, database schema, and email service integration
- QA gate validates each specialist's output before the Manager moves on

---

**Plan a startup MVP**
```
Enter your goal: I'm building a SaaS tool for freelancers to manage
invoices and track time. Help me plan the MVP backend and the AI
features I should prioritize.
```
- `project-manager` → MVP scope, milestones, what to cut for v1
- `backend-architect` → data model for invoices/time entries, API design
- `ai-engineer` → smart categorization, anomaly detection for hours logged

---

**Research and plan a technical decision**
```
Enter your goal: We need to choose between PostgreSQL and MongoDB for
our new social app. Research the tradeoffs and give me a recommendation
with a migration/setup plan.
```
- `backend-architect` → tradeoff analysis, recommendation, schema examples
- `project-manager` → phased rollout plan, risk register

---

**Automate a recurring work process**
```
Enter your goal: I run a weekly team standup digest. Help me design a
system that collects status updates from Slack, summarizes them with AI,
and sends a report to our manager.
```
- `ai-engineer` → summarization pipeline design
- `backend-architect` → Slack integration, scheduler, delivery mechanism
- `project-manager` → implementation phases, dependencies

---

## Adding Your Own Specialist

Drop a markdown file in `agents/` — the system discovers it automatically.

```
agents/
  your-specialist.md
```

Use this structure (inspired by [agency-agents](https://github.com/msitarzewski/agency-agents)):

```markdown
# Your Specialist Name

## Identity
Who this agent is and how they think.

## Mission
What they are responsible for delivering.

## Expertise
- Skill 1
- Skill 2

## Deliverables
- Concrete output 1
- Concrete output 2

## Success Metrics
- How you know the output is good

## Workflow
1. Step one
2. Step two
```

Then in your goal, the Manager will automatically consider this specialist
when deciding who to assign subtasks to.

---

## Extending the Agent

**Add a new tool to `workflow_agent.py`:**

1. Write the Python function:
```python
def set_priority(task_id: str, priority: str) -> dict:
    tasks[task_id]["priority"] = priority
    return {"ok": True, "task": tasks[task_id]}
```

2. Register it:
```python
TOOL_FUNCTIONS = {
    ...
    "set_priority": set_priority,
}
```

3. Add the schema so Claude knows it exists:
```python
TOOLS = [
    ...
    {
        "name": "set_priority",
        "description": "Set task priority to low, medium, or high.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id":  {"type": "string"},
                "priority": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["task_id", "priority"],
        },
    },
]
```

---

## Experiment Branches

```
main                         ← stable base
experiment/add-priority      ← adds priority field + set_priority tool
experiment/file-persistence  ← saves tasks to tasks.json between runs
experiment/multi-agent       ← multi_agent.py + multi_agent_v2.py
```

Switch between them to see how each feature was added:
```bash
git checkout experiment/add-priority
git checkout main
```

---

---

## Data Engineer Scenarios

A ready-to-run script with 8 pre-built goals covering common data engineering work.

```bash
python3 data_engineer_scenarios.py
```

Pick a number, or type `0` to enter your own goal.

### What's included

| # | Scenario | Tags |
|---|---|---|
| 1 | Design a new ingestion pipeline | pipeline, airflow, incremental load |
| 2 | Build a dbt project for e-commerce | dbt, modeling, BigQuery |
| 3 | Debug a failing pipeline | incident, runbook, SQL diagnostics |
| 4 | Design a data quality framework | dbt tests, data contracts, alerting |
| 5 | Plan a warehouse migration | Redshift → Snowflake, risk register |
| 6 | Design a real-time streaming pipeline | Kafka, Flink, late events |
| 7 | Set up data observability | monitoring, freshness, lineage |
| 8 | Optimize a slow dbt model | BigQuery, partitioning, incremental |

### Which specialists run

Each scenario automatically routes subtasks to the right agent:

- **data-engineer** — pipeline design, DAG specs, SQL, dbt models
- **data-quality** — quality checks, data contracts, dbt test YAML
- **project-manager** — phased plans, risk registers, migration sequencing
- **backend-architect** — API/infra pieces (e.g. streaming sinks, storage design)

The **Reality Checker** QA agent validates every output before the Manager accepts it.
If an output is too vague or misses the point, the specialist retries up to 3 times.

### Adding your own data scenario

You can add to `SCENARIOS` in `data_engineer_scenarios.py`:

```python
{
    "name": "Your scenario name",
    "tags": ["tag1", "tag2"],
    "goal": (
        "Detailed description of what you need. Be specific: "
        "name the tools you use, the scale of data, the output you want."
    ),
},
```

Or just run the script and pick `0` to type a one-off goal.

### Tips for writing good goals

The more specific you are, the better the output:

| Vague | Specific |
|---|---|
| "Design a pipeline" | "Design an hourly Airflow DAG that pulls from Postgres into Snowflake using incremental loads based on `updated_at`" |
| "Check data quality" | "Write dbt tests for a `transactions` table: null checks on `amount` and `user_id`, referential integrity to `users`, and a freshness check" |
| "Help with dbt" | "We have raw Shopify data in BigQuery. Design the staging → mart dbt layer for orders and customers, including model names, grain, and key tests" |

---

## Project Credits

Agent persona patterns inspired by [agency-agents](https://github.com/msitarzewski/agency-agents) by [@msitarzewski](https://github.com/msitarzewski).
