# Agent Studio

A wrapper around Claude that coordinates specialist AI agents to handle multi-step tasks. You describe what you need, discuss the approach with a manager agent, and a team of specialists does the work — using the tools you've already connected to Claude.

It's not a replacement for Claude. It's a way to use your existing Claude subscription more efficiently for bigger tasks.

---

## What it actually does

1. You describe a task
2. A manager agent discusses the approach with you (like a 1-on-1 with a project lead)
3. When you're happy, the manager delegates to specialist agents
4. Independent tasks run in parallel to save time
5. You review each output before it's accepted
6. Results are saved as real files (code, documents, etc.)

Your Claude integrations (Notion, Slack, GitHub, etc.) are auto-detected and available to workers. No extra setup.

## What it does NOT do

- It does not replace Claude for quick questions or simple tasks — just use Claude directly for those
- It does not have internet access unless you connect tools
- Agents work from Claude's training data and connected tools — they cannot access systems you haven't explicitly connected
- If an agent doesn't know something, it should say so rather than make something up

---

## Quick Start

Requires the [Claude CLI](https://claude.ai/code):

```bash
npm install -g @anthropic-ai/claude-code
claude login
```

Then install Agent Studio:

```bash
git clone --recursive https://github.com/anjolok1997/agent-studio.git
cd agent-studio
pip install -e .
studio
```

That's it. Works from any folder. No API key needed — uses your Claude subscription.

---

## How it works

```
> Design a REST API for a task management app

  Integrations: Notion, Slack

  Manager is reviewing your goal...

  ┌─ Manager ──────────────────────────────────────────┐
  │ I'd split this into schema design and API routes   │
  │ — both can run in parallel. Then a third pass to   │
  │ wire up auth. I see you have Notion connected, so  │
  │ I can save the spec there too. Sound good?         │
  └────────────────────────────────────────────────────┘

  You > go

  Running 2 tasks in parallel...
  ▶ data-engineer — Design database schema
  ▶ backend-architect — Design API routes and endpoints
  All 2 parallel tasks complete.

  ▶ backend-architect — Add authentication layer

  Project created: output/project
    schema.sql
    src/app.py
    src/routes.py
    src/auth.py
    requirements.txt
    Dockerfile

  Done. 6 files created.
```

---

## Your tools, no extra setup

Agent Studio auto-detects what you've already connected to Claude:

```
  Integrations: Notion, Slack, Clickhouse
```

If you've connected Notion to Claude, Agent Studio can write to it. If you've connected Slack, agents can search your channels. No tokens to paste, no config files.

For local tools (filesystem, databases), use the interactive setup:

```bash
studio mcp add       # Pick from curated, version-pinned servers
studio mcp list      # Show what's configured
studio mcp remove    # Remove a server
```

All MCP packages are pinned to exact audited versions. If Docker is installed, servers run in sandboxed containers. See [Security](#security) below.

---

## Rules agents follow

These rules are built into every agent to reduce hallucination and keep things honest:

- **Do what was asked, nothing more.** Agents should not add features, refactor code, or make "improvements" beyond the task.
- **Say "I don't know" when you don't know.** If an agent can't complete a task with the information available, it should say so — not guess.
- **Don't make up data.** If agents don't have access to a system, they should not fabricate responses. If a tool isn't connected, say that.
- **Use connected tools for real data.** When Notion, Slack, databases, or other tools are available, use them instead of generating from memory.
- **Don't hallucinate file contents.** If asked to read or analyze a file, agents must use actual tool access — not imagine what the file might contain.
- **Be specific about limitations.** If a task requires something the agent can't do (e.g. deploy code, send emails without the right tool), say what's missing.
- **One task, one deliverable.** Each agent produces what was asked for — not a meta-commentary about what they would do.

---

## Agents

Agent Studio ships with **159 specialist agents** across categories like engineering, marketing, design, research, data, and more. The right team is assembled automatically based on your task.

Simple tasks get 1 agent. Complex tasks get 3-4. The system assesses complexity before picking a team — it won't over-staff a simple job.

Type `pick` at launch to browse and hand-pick agents, or type `templates` for pre-built setups.

Agent library from [agency-agents](https://github.com/msitarzewski/agency-agents) (MIT License).

### Add your own

Drop a `.md` file in `agents/`. Discovered automatically on next launch.

---

## Speed options

| Option | Manager | Workers | Best for |
|---|---|---|---|
| **Fast** | Haiku | Haiku | Quick tasks, summaries |
| **Balanced** (default) | Sonnet | Haiku | Most tasks |
| **Powerful** | Opus | Sonnet | Complex analysis, deep research |

---

## Security

Agent Studio runs third-party MCP server packages. We treat them as untrusted code.

| Protection | What it does |
|---|---|
| **Curated allowlist** | Only verified servers from official publishers |
| **Pinned versions** | Every package locked to an exact version |
| **Docker sandbox** | MCP servers run in isolated containers (when Docker is installed) |
| **`--ignore-scripts`** | npm postinstall scripts disabled |
| **`--network=none`** | Servers that don't need internet get no network access |
| **Custom servers blocked** | `--allow-custom` flag required for unverified packages |
| **Tool risk classification** | Dangerous operations require approval |
| **Spending limits** | Hard cap with warnings at 50%, 75%, 90% |
| **User spot-check** | You review each worker's output before it's accepted |
| **Audit trail** | Every decision logged to `logs/` |

Without Docker, MCP servers run directly with pinned versions. A warning is shown recommending Docker.

---

## Templates

Pre-built setups for common tasks. Type `templates` at launch.

| Template | Team | Use Case |
|---|---|---|
| Study Guide Builder | educator, researcher, summarizer | Create study materials |
| Data Pipeline Design | data-engineer, backend-architect, PM | Design pipelines |
| Code Review | code-reviewer, backend-architect, PM | Security, quality |
| Content Creation | writer, researcher, PM | Blog posts, docs |
| + 7 more | ... | Business analysis, UX audit, research, etc. |

Or just describe what you need — no template required.

---

## Recurring Tasks

```bash
studio schedule add             # Create a recurring task
studio schedule list            # Show all schedules
studio schedule run             # Run all due tasks now
studio schedule daemon          # Run continuously in background
```

---

## All Options

```bash
studio                              # Describe your task
studio mcp add                      # Add an MCP server
studio mcp list                     # Show configured servers
studio schedule add                 # Create a recurring task
studio --classic-plan               # Use old planner instead of manager briefing
studio --no-plan                    # Skip the briefing
studio --supervised                 # Approve every step manually
studio --use-integrations           # Force enable Claude integrations
studio --worker-model sonnet        # Upgrade workers to Sonnet
studio --manager-model opus         # Upgrade manager to Opus
studio --execute --env dev          # Enable real tool actions
studio --execute --env prod         # Production (requires confirmation)
studio --token-limit 50000          # Lower spending cap
studio --show-models                # Show available models
```

---

## Documentation

See [`docs/`](docs/) for technical details:

- [Architecture](docs/architecture.md) — System design and data flow
- [Safety](docs/safety.md) — Permissions, spending, audit
- [Extending](docs/extending.md) — Add agents, templates, MCP, visualizers

---

## License

MIT — see [LICENSE](LICENSE).

## Credits

Agent library from [agency-agents](https://github.com/msitarzewski/agency-agents) by [@msitarzewski](https://github.com/msitarzewski) (MIT License).
