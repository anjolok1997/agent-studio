# What is Agent Studio?

Agent Studio is a multi-agent AI tool that gets tasks done faster and cheaper than a single AI chat. Describe what you need, and a team of specialist agents handles it — from a quick summary to a deep research project.

Instead of one long back-and-forth conversation with an AI, Agent Studio splits the work across focused specialists who each do their part. A manager coordinates, a QA agent checks the output, and you get the result.

---

## The Problem It Solves

Using a single AI chat for complex tasks is slow, expensive, and messy. You end up re-prompting, losing context, and paying for a powerful model to do simple subtasks.

Agent Studio fixes this:
- A cheap, fast model (Haiku) handles the focused subtasks
- A smarter model (Sonnet/Opus) coordinates the big picture
- Each specialist stays focused on what they're good at
- Quality is checked automatically before results come back to you

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

Safety is built in — you don't need to think about it:
- **Tools are sandboxed** — dangerous operations are blocked unless you explicitly enable them
- **You see the plan first** — nothing runs until you approve
- **Spending is capped** — hard limit prevents runaway usage
- **Quality is checked** — a QA agent validates every output
- **Everything is logged** — full audit trail in `logs/`

---

## What Can You Use It For?

| Task | What happens |
|---|---|
| "Summarize this doc and list action items" | Summarizer + analyst work together |
| "Design a data pipeline from Postgres to Snowflake" | Data engineer + architect + PM collaborate |
| "Review this code for security issues" | Code reviewer + security engineer audit it |
| "Research competitors and compare pricing" | Researcher + analyst produce a comparison |
| "Create a study guide for distributed systems" | Educator + researcher build structured materials |
| "Write a blog post about our new feature" | Writer + researcher draft and fact-check |
| Anything else | Describe it — the right team gets assembled |

Works for quick tasks and deep research alike.

---

## Good to Know

- **Safe by default.** Agents can research, analyze, and draft — but can't touch real systems unless you opt in with `--execute`.
- **Task-oriented, not a chatbot.** You describe what you need, agents deliver results. No back-and-forth conversation.
- **Real tool access is opt-in.** Connect to databases, APIs, and services via MCP when you're ready.

---

## Tech Stack

- **LLM**: Claude — sign in via Claude CLI (default) or use an Anthropic API key
- **CLI integration**: Uses the [Claude CLI](https://claude.ai/code) for authentication
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
