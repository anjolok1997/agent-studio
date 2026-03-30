# What is Agent Studio?

Agent Studio is a multi-agent AI platform that assembles teams of specialist AI agents to work on projects together. You give it a goal, it breaks the work into subtasks, assigns each subtask to the right specialist, validates the output, and delivers a final result.

Think of it like a company where you're the CEO. You set the direction, and your team of specialists handles the execution. You only get pulled in when something important needs your sign-off.

---

## The Problem It Solves

A single AI prompt can only do one thing at a time. For complex tasks — designing a data pipeline, auditing a UX flow, writing a business analysis — you need multiple perspectives working together: a researcher, an architect, a reviewer, a project manager.

Agent Studio automates this. Instead of prompting one agent repeatedly, you describe the goal once and let a team handle it.

---

## How It Works (Simple Version)

```
You: "Design an hourly Airflow DAG that pulls from Postgres into Snowflake"

Agent Studio:
  1. Manager breaks this into subtasks
  2. Data Engineer designs the DAG structure
  3. Backend Architect defines the Snowflake schema
  4. Project Manager creates the monitoring plan
  5. QA Agent validates each output
  6. Manager synthesizes everything into a final deliverable
```

You see a plan before anything runs, and you get the final summary + all artifacts at the end.

---

## Key Concepts

### Agents

Agents are AI specialists with defined personas — an identity, expertise, mission, and workflow. Each agent is a markdown file that becomes a system prompt for Claude.

Agent Studio ships with **159 agents** across 13 categories (engineering, design, marketing, sales, etc.) from the [agency-agents](https://github.com/msitarzewski/agency-agents) library. You can also create your own.

### Templates

Templates are pre-built project configurations. They define which agents to use and what goal to pursue. Examples: Data Pipeline Design, UX Audit, Code Review, Study Guide Builder.

Pick a template to get started fast, or choose "Custom project" to assemble your own team.

### Manager and Workers

- **Manager agent** (Claude Sonnet) — Receives the goal, breaks it into subtasks, assigns each to a specialist, and synthesizes the final result.
- **Worker agents** (Claude Haiku) — Each worker runs one subtask using their specialist persona. They can research, draft outputs, and flag blockers.
- **Quality gate** (Claude Haiku) — A "reality checker" agent that validates every worker output before it goes back to the manager.

### CEO Mode

By default, you're in CEO mode. The agents run autonomously and only escalate to you when something genuinely needs human judgment:
- Dangerous actions (deploying, running SQL, shell commands)
- Production-targeting operations
- Budget threshold crossed
- A worker is stuck and flags a blocker

Everything else — task planning, research, drafting, QA — runs without interruption.

### Tools

Agents have access to tools:
- **research** — Deep-dive into a topic
- **draft_output** — Produce an artifact (plan, spec, code, checklist)
- **flag_blocker** — Signal that something is stuck

In dry-run mode (default), tools return simulated responses. In execute mode (`--execute`), tools connect to real systems via MCP (Model Context Protocol) — real databases, file systems, APIs.

### Safety

Multiple layers prevent agents from doing anything unintended:
- **Dry-run mode** blocks dangerous tools by default
- **Tool risk classification** (safe / sensitive / dangerous)
- **Spending cap** limits token usage per run
- **CEO escalation** pauses for human approval on critical actions
- **Audit log** records every decision for traceability

---

## What Can You Build With It?

| Use Case | Template | What You Get |
|---|---|---|
| Study materials | Study Guide Builder | Structured guide with prerequisites, explanations, practice questions |
| Data pipeline design | Data Pipeline Design | DAG structure, schema definitions, monitoring plan |
| UX audit | UX Audit | User journey map, friction points, accessibility findings |
| Market analysis | Business Analysis | KPIs, SWOT analysis, recommendation |
| Technical blog post | Content Creation | Drafted article with research backing |
| Code security review | Code Review | Vulnerability findings, performance issues, test gaps |
| Document summary | Doc Summarizer | Key points extracted from large documents |
| Custom project | (pick your own team) | Whatever you need |

---

## What It's Not

- **Not an autonomous agent that takes real actions by default.** Dry-run mode is the default. Real actions require explicit opt-in (`--execute`).
- **Not a chatbot.** You set a goal, agents execute, and you get results. It's task-oriented, not conversational.
- **Not a code execution environment.** Agents reason and plan, but code execution happens through MCP tools connected to real systems, not inside Agent Studio itself.

---

## Tech Stack

- **LLM**: Claude — works with your subscription (default) or Anthropic API key
- **CLI integration**: Uses the [Claude CLI](https://claude.ai/code) for subscription-based access
- **Language**: Python 3.9+
- **Agent library**: [agency-agents](https://github.com/msitarzewski/agency-agents) (MIT License)
- **Real tool integration**: MCP (Model Context Protocol)
- **Visualization**: WebSocket events for external plugins

---

## Next Steps

- [Quick Start](../README.md#quick-start) — Get running in 4 commands
- [Architecture](architecture.md) — How the system is built
- [Agent System](agents.md) — How agents work, library vs local
- [Oversight Modes](oversight.md) — CEO mode vs Supervised mode
- [Safety](safety.md) — Permissions, spending, audit
- [Extending](extending.md) — Add agents, templates, MCP servers
