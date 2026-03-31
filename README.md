# Agent Studio

Describe what you need. A team of AI specialists gets it done — fast and cheap.

Whether it's a quick task or a deep research project, Agent Studio breaks it down, picks the right specialists, and delivers results. You stay in control without micromanaging.

---

## Quick Start

```bash
git clone --recursive https://github.com/anjolok1997/agent-studio.git
cd agent-studio
pip3 install -r requirements.txt
python3 launch.py
```

Sign in via the [Claude CLI](https://claude.ai/code). If you haven't already:

```bash
npm install -g @anthropic-ai/claude-code
claude login
```

That's it. No API key needed.

---

## How It Works

```
> Summarize this 50-page PDF and pull out the action items

Assembling team...
  Team: Summarizer, Researcher, Analyst

Planning...
  1. [summarizer] Extract key points from each section
  2. [researcher] Cross-reference claims and flag gaps
  3. [analyst] Compile action items with priorities

Proceed? [Y/n]: y

  ... agents working ...

Done. 3 artifacts produced.
```

Just describe what you need. Agent Studio:
1. Picks the right specialists from 159 available agents
2. Shows you the plan before any work starts
3. Runs the team autonomously
4. Delivers a summary + artifacts

### What can you use it for?

| Task | What happens |
|---|---|
| "Summarize this doc and list action items" | Summarizer extracts key points, analyst compiles actions |
| "Design a data pipeline from Postgres to Snowflake" | Data engineer + backend architect + PM collaborate |
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

## Built-in Safety

Agent Studio is designed to be safe by default. You don't need to configure anything — protections are always on.

| What | How |
|---|---|
| **Plan before action** | You see the full plan and approve before any work starts |
| **Tools are sandboxed** | Dangerous operations (SQL, deploy, shell) are blocked unless you explicitly enable them |
| **Spending limits** | Hard cap prevents runaway token usage |
| **Quality checks** | A QA agent validates every output before it's finalized |
| **Full audit trail** | Every decision logged to `logs/` — who did what, when, why |
| **You approve what matters** | Agents only ask you for sign-off on critical actions (production, dangerous tools) |

### Connecting to real systems

By default, tools are simulated — nothing leaves the sandbox. Ready-to-use configs are in [`examples/mcp/`](examples/mcp/):

```bash
# Read and analyze local files
cp examples/mcp/filesystem.yaml mcp_config.yaml
python3 launch.py --execute --env dev

# Review GitHub PRs, issues, and code
cp examples/mcp/github.yaml mcp_config.yaml
python3 launch.py --execute --env dev

# Build your own — blank starter with all common servers
cp examples/mcp/custom.yaml mcp_config.yaml
```

Supports: Filesystem, GitHub, PostgreSQL, SQLite, Slack, Puppeteer, Web Fetch, and any [MCP server](https://github.com/modelcontextprotocol/servers).

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
python3 launch.py schedule add             # Create a recurring task
python3 launch.py schedule list            # Show all schedules
python3 launch.py schedule run             # Run all due tasks now
python3 launch.py schedule run pr-digest   # Run a specific one
python3 launch.py schedule daemon          # Run continuously in background
python3 launch.py schedule remove pr-digest  # Remove a schedule
```

Example: a weekly PR digest that runs every Monday:

```
$ python3 launch.py schedule add

Name: pr-digest
Task: Summarize all GitHub PRs from the last week, flag stale ones, list any security concerns
How often? weekly
Agents (Enter to auto-suggest):

Scheduled: pr-digest
Runs every 168h | Goal: Summarize all GitHub PRs...
```

Schedules are saved as YAML in `schedules/`. Run results go to `runs/`.

---

## All Options

```bash
python3 launch.py                              # Just describe your task (default)
python3 launch.py schedule add                 # Create a recurring task
python3 launch.py schedule daemon              # Run scheduler in background
python3 launch.py --api-key                    # Use Anthropic API key instead of CLI login
python3 launch.py --supervised                 # Full control: approve every step
python3 launch.py --worker-model sonnet        # Upgrade workers to Sonnet
python3 launch.py --manager-model opus         # Upgrade manager to Opus
python3 launch.py --no-plan                    # Skip the planning preview
python3 launch.py --execute --env dev          # Enable real tool actions
python3 launch.py --execute --env prod         # Production (requires confirmation)
python3 launch.py --token-limit 50000          # Lower spending cap
python3 launch.py --mcp-config mcp.yaml        # Connect real tools via MCP
python3 launch.py --show-models                # Show available models
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
