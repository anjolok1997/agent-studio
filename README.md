# Agent Studio

Describe what you need. A team of AI specialists gets it done — fast and cheap.

Whether it's a quick task or a deep research project, Agent Studio breaks it down, picks the right specialists, and delivers results. You stay in control without micromanaging.

---

## Quick Start

```bash
pip install agent-studio
studio
```

That's it. Works from any folder. Requires the [Claude CLI](https://claude.ai/code) for sign-in:

```bash
npm install -g @anthropic-ai/claude-code
claude login
```

Or install from source:

```bash
git clone --recursive https://github.com/anjolok1997/agent-studio.git
cd agent-studio
pip install -e .
studio
```

No API key needed.

---

## How It Works

```
> Design a data pipeline from Postgres to Snowflake

Manager is reviewing your goal...

┌─ Manager ──────────────────────────────────────────────┐
│ Good goal. Here's my take: I'd start with the data     │
│ engineer on schema mapping, then the backend architect  │
│ on the ETL design. Both can run in parallel since       │
│ they're independent. Then the PM sequences it all.      │
│                                                        │
│ Is this a one-time migration or ongoing sync?           │
└────────────────────────────────────────────────────────┘

You > ongoing, just the orders and customers tables

┌─ Manager ──────────────────────────────────────────────┐
│ Got it. I'll narrow the scope. Say 'go' when ready.    │
└────────────────────────────────────────────────────────┘

You > go

  Running 2 tasks in parallel...
  ▶ data-engineer — Design schema mapping for orders + customers
  ▶ backend-architect — Design incremental ETL pipeline
  All 2 parallel tasks complete.

  ▶ project-manager — Sequence deployment plan from both outputs

Done.
```

Just describe what you need. Agent Studio:
1. **Briefs you first** — a manager agent discusses the approach with you before work begins
2. Picks the right specialists from 159 available agents
3. **Runs workers in parallel** when tasks are independent
4. You **spot-check each output** before the manager continues
5. Delivers a summary + artifacts

### What can you use it for?

| Task | What happens |
|---|---|
| "Summarize this doc and list action items" | Summarizer extracts key points, analyst compiles actions |
| "Design a data pipeline from Postgres to Snowflake" | Data engineer + backend architect collaborate in parallel |
| "Review this code for security issues" | Code reviewer + security engineer audit together |
| "Research competitors and compare pricing" | Researcher + analyst produce a comparison table |
| "Create a study guide for distributed systems" | Educator + researcher build structured materials |
| "Write a blog post about our new feature" | Writer + researcher draft and fact-check |

Works for quick tasks and deep projects alike.

---

## 159 Agents, Ready to Go

Agent Studio ships with **147 specialist agents** across 13 categories, plus **12 built-in agents**. The right team is assembled automatically based on what you ask for.

| Category | Count | Examples |
|---|---|---|
| Engineering | 26 | Backend Architect, SRE, Security, DevOps, Frontend |
| Marketing | 29 | SEO, Content, Social, Brand Voice, Email |
| Specialized | 28 | Legal, Financial, Healthcare, Grant Writing |
| Design | 8 | UX Architect, UI Designer, Brand Guardian |
| Testing | 8 | QA Lead, Performance, Accessibility |
| + 8 more | 48 | Academic, Product, Sales, Strategy, Support, ... |

Type `pick` at launch to browse and hand-pick agents, or type `templates` for pre-built setups.

Agent library from [agency-agents](https://github.com/msitarzewski/agency-agents) (MIT License).

### Add your own

Drop a `.md` file in `agents/`. Discovered automatically.

```markdown
# Your Specialist

## Identity
Who this agent is.

## Mission
What they deliver.

## Expertise
- Skill 1
- Skill 2
```

---

## Pick Your Speed

Choose at launch, or set via CLI flags:

| Option | Manager | Workers | Best for |
|---|---|---|---|
| **Fast** | Haiku | Haiku | Quick tasks, summaries |
| **Balanced** (default) | Sonnet | Haiku | Most tasks |
| **Powerful** | Opus | Sonnet | Complex analysis, deep research |

---

## Connect Real Tools (MCP)

Agent Studio connects to real systems via the [Model Context Protocol](https://modelcontextprotocol.io/). Workers can query databases, read GitHub PRs, search Slack — not just generate text.

### Interactive setup

```bash
studio mcp add       # Pick a server from the curated list
studio mcp list      # Show configured servers
studio mcp remove    # Remove a server
```

### Available servers (curated, version-pinned)

| Server | What agents can do |
|---|---|
| **GitHub** | Read repos, review PRs, search code, manage issues |
| **Filesystem** | Read/write local files, search directory contents |
| **PostgreSQL** | Query and inspect your database |
| **Slack** | Search messages, read channels, send updates |
| **Puppeteer** | Browse web pages, fill forms, extract data |
| **Redis** | Inspect keys and data |

All packages are pinned to exact audited versions. See [Security](#security) for details.

Ready-to-use example configs in [`examples/mcp/`](examples/mcp/).

---

## Security

Agent Studio takes supply chain security seriously. MCP servers are third-party npm packages that run with your permissions — we treat them as untrusted code.

### Protections

| Layer | What it does |
|---|---|
| **Curated allowlist** | Only 6 verified servers from `@modelcontextprotocol` (official publisher) |
| **Pinned versions** | Every package locked to an exact version — no `@latest` |
| **Docker sandbox** | When Docker is installed, MCP servers run in isolated containers |
| **`--ignore-scripts`** | npm postinstall scripts disabled (prevents malware like the axios attack) |
| **`--cap-drop=ALL`** | Containers drop all Linux capabilities |
| **`--read-only`** | Container filesystem is read-only |
| **`--network=none`** | Servers that don't need internet (filesystem) get no network access |
| **Custom servers blocked** | `--allow-custom` flag required to add unverified packages |
| **Tool risk classification** | Dangerous operations (delete, deploy, execute) require approval |
| **Spending limits** | Hard cap prevents runaway token usage |
| **Full audit trail** | Every decision logged to `logs/` |

### Without Docker

If Docker isn't installed, MCP servers run directly via `npx` with pinned versions. You'll see a warning recommending Docker. Install Docker for full protection: https://docs.docker.com/get-docker/

---

## Built-in Safety

| What | How |
|---|---|
| **Briefing before action** | Manager discusses approach with you before agents start working |
| **User spot-check** | You review each worker's output before it's accepted (approve / feedback / skip) |
| **Tools are sandboxed** | Dangerous operations blocked unless you explicitly enable them |
| **Spending limits** | Hard cap prevents runaway token usage |
| **Full audit trail** | Every decision logged to `logs/` |
| **You approve what matters** | Agents only ask for sign-off on critical actions (production, dangerous tools) |

```bash
studio --execute --env dev          # Enable real actions in dev
studio --execute --env prod         # Production (extra confirmation required)
```

---

## Templates

Pre-built setups for common tasks. Type `templates` at launch.

| Template | Team | Use Case |
|---|---|---|
| Study Guide Builder | educator, researcher, summarizer | Create study materials |
| Data Pipeline Design | data-engineer, backend-architect, PM | Design pipelines |
| UX Audit | ux-designer, analyst, PM | Audit user flows |
| Business Analysis | analyst, researcher, PM | Market analysis, SWOT |
| Content Creation | writer, researcher, PM | Blog posts, docs |
| Code Review | code-reviewer, backend-architect, PM | Security, quality |
| + 3 more | ... | Data quality, doc summary, research |

Or just describe what you need — no template required.

---

## Recurring Tasks

Set up tasks that run on a schedule — weekly digests, daily summaries, recurring checks.

```bash
studio schedule add             # Create a recurring task
studio schedule list            # Show all schedules
studio schedule run             # Run all due tasks now
studio schedule daemon          # Run continuously in background
```

---

## All Options

```bash
studio                              # Just describe your task (default)
studio mcp add                      # Add an MCP server (interactive)
studio mcp list                     # Show configured servers
studio mcp remove <name>            # Remove a server
studio schedule add                 # Create a recurring task
studio schedule daemon              # Run scheduler in background
studio --api-key                    # Use Anthropic API key instead of CLI login
studio --supervised                 # Full control: approve every step
studio --classic-plan               # Use old Haiku planner instead of manager briefing
studio --no-plan                    # Skip the briefing/planning phase
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

- [What is Agent Studio?](docs/what-is-agent-studio.md) — Overview and key concepts
- [Architecture](docs/architecture.md) — System design and data flow
- [Oversight Modes](docs/oversight.md) — How safety and approvals work
- [Agent System](docs/agents.md) — Library agents, local agents, loading
- [Safety](docs/safety.md) — Permissions, spending, audit
- [Extending](docs/extending.md) — Add agents, templates, MCP, visualizers

---

## Credits

Agent library from [agency-agents](https://github.com/msitarzewski/agency-agents) by [@msitarzewski](https://github.com/msitarzewski) (MIT License).
