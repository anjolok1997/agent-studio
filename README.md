# Agent Studio

Assemble a team of AI specialists, give them a goal, and let them work. You're the CEO — they handle the details and only come to you when it matters.

Works with your Claude subscription — no API key needed. Agent personas powered by [agency-agents](https://github.com/msitarzewski/agency-agents).

---

## Quick Start

```bash
git clone --recursive https://github.com/anjolok1997/agent-studio.git
cd agent-studio
pip3 install -r requirements.txt
python3 launch.py
```

That's it. Agent Studio uses your Claude subscription via the [Claude CLI](https://claude.ai/code). If you haven't already, install and log in:

```bash
npm install -g @anthropic-ai/claude-code
claude login
```

### API Key Mode (alternative)

If you prefer pay-per-token pricing via the Anthropic API:

```bash
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > .env
python3 launch.py --api-key
```

Get a key at [console.anthropic.com](https://console.anthropic.com).

---

## How It Works

```
1. Pick a template (or build a custom team)
2. Provide materials (documents, context)
3. Review the execution plan (cost, time, tokens)
4. Agents run autonomously
5. You only intervene for critical actions
6. Get final summary + artifacts
```

### CEO Mode (default)

Agents work independently. You only get pulled in when something serious needs sign-off:

| You get asked when... | Example |
|---|---|
| Dangerous tool call | `deploy`, `run_sql`, `shell_exec` |
| Production target | Any write action when `--env prod` |
| Spending threshold | 80% of token budget used |
| Worker is stuck | Agent flags a blocker it can't resolve |

Everything else — task breakdown, research, drafting, QA — happens without interruption.

### Supervised Mode (legacy)

Want more control? Use `--supervised` for the old behavior: checkpoints after every subtask, per-delegation approval.

```bash
python3 launch.py --supervised
```

---

## 159 Agents, Ready to Go

Agent Studio ships with **147 specialist agents** from the [agency-agents](https://github.com/msitarzewski/agency-agents) library across 13 categories, plus **12 built-in agents** for common tasks.

| Category | Agents | Examples |
|---|---|---|
| Engineering | 26 | Backend Architect, SRE, Security Engineer, DevOps |
| Marketing | 29 | SEO Strategist, Content Marketer, Brand Voice |
| Specialized | 28 | Legal Analyst, Financial Modeler, Grant Writer |
| Design | 8 | UX Architect, UI Designer, Brand Guardian |
| Game Dev | 5 | Narrative Designer, Level Designer |
| Sales | 8 | Account Strategist, Outreach Specialist |
| Testing | 8 | QA Lead, Performance Tester, Accessibility |
| + 6 more | ... | Academic, Product, Strategy, Support, ... |

When you pick "Custom project", you'll see the full menu grouped by category:

```
Available agents (147 library + 12 custom):

  engineering (26)
      1. Backend Architect — Senior backend architect specializing in...
      2. Code Reviewer — Expert code reviewer focused on...
      3. Security Engineer — Application security specialist...
      ...

  design (8)
     27. UI Designer — ...
     ...

  custom (12)  <-- your local agents
    148. backend-architect (local)
     ...

Enter agent numbers: 1,3,27
Or type a category name: engineering
```

### Add Your Own Agents

Drop a `.md` file in `agents/` — it's discovered automatically and overrides any library agent with the same name.

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
```

---

## Templates

Templates are pre-built project configurations that pick the right agents for common tasks.

| Template | Team | Use Case |
|---|---|---|
| Study Guide Builder | educator, researcher, summarizer | Create study materials |
| Data Pipeline Design | data-engineer, backend-architect, PM | Design Airflow/dbt pipelines |
| UX Audit | ux-designer, analyst, PM | Audit user flows, accessibility |
| Business Analysis | analyst, researcher, PM | Market analysis, SWOT, KPIs |
| Content Creation | writer, researcher, PM | Blog posts, docs, proposals |
| Code Review | code-reviewer, backend-architect, PM | Security, performance, quality |
| Data Quality | data-quality, data-engineer, PM | dbt tests, data contracts |
| Doc Summarizer | summarizer, researcher | Summarize large documents |
| Research Assistant | researcher, analyst | Literature review, comparisons |

Or pick **Custom project** to choose any agents and write your own goal.

### Create a Template

Add a `.yaml` file to `templates/`:

```yaml
name: "Your Template Name"
description: "One-line description"
agents:
  - engineering-backend-architect
  - engineering-security-engineer
goal: >
  Your default goal. Be specific about tools, scale, and output.
materials:
  - label: "Input name"
    type: text
    hint: "What to provide here"
    required: false
```

---

## Model Selection

| Model | Speed | Cost | Best For |
|---|---|---|---|
| `haiku` | Fastest | Cheapest | Simple tasks, summaries |
| `sonnet` | Fast | Moderate | Complex reasoning, planning |
| `opus` | Slower | Expensive | Deep analysis, nuanced tasks |

```bash
python3 launch.py --worker-model sonnet
python3 launch.py --manager-model opus
python3 launch.py --show-models
```

---

## Safety

| Layer | What it does | Default |
|---|---|---|
| **Subscription Mode** | Uses Claude CLI — no API key needed | On |
| **CEO Mode** | Agents run autonomously, escalate only for critical actions | On |
| **Execution Plan** | Preview subtasks + cost/time estimates before spending tokens | On |
| **Dry-Run Mode** | Dangerous tools blocked entirely | On |
| **Spending Cap** | Hard limit on tokens per run (100k default) | On |
| **Quality Gate** | QA agent validates every worker output | On |
| **Audit Log** | Full trace of every decision in `logs/` | On |
| **Tool Risk Classification** | Safe / Sensitive / Dangerous | On |

### Tool Risk Levels

| Risk | Examples | Dry-Run | Execute Mode |
|---|---|---|---|
| **Safe** | research, analyze | Allowed | Allowed |
| **Sensitive** | draft_output, create_file | Allowed | Auto-approved (CEO) |
| **Dangerous** | run_sql, deploy, shell_exec | Blocked | CEO approval required |

### Execute Mode

Enable real actions (tool calls go through MCP to real systems):

```bash
python3 launch.py --execute --env dev        # Dev environment
python3 launch.py --execute --env staging    # Staging
python3 launch.py --execute --env prod       # Production (extra warnings)
```

---

## Connect Real Tools (MCP)

Use the [Model Context Protocol](https://modelcontextprotocol.io/) to connect agents to real databases, APIs, and services:

```bash
cp mcp_config.example.yaml mcp_config.yaml
# Edit with your server details
python3 launch.py --mcp-config mcp_config.yaml --execute
```

---

## All Options

```bash
python3 launch.py                              # Subscription mode + CEO mode (default)
python3 launch.py --api-key                    # Use Anthropic API key instead
python3 launch.py --supervised                 # Legacy: checkpoints + approvals
python3 launch.py --worker-model sonnet        # Sonnet for workers
python3 launch.py --manager-model opus         # Opus for manager
python3 launch.py --no-plan                    # Skip planning phase
python3 launch.py --execute --env dev          # Enable real actions
python3 launch.py --execute --env prod         # Production (requires confirmation)
python3 launch.py --token-limit 50000          # Lower spending cap
python3 launch.py --mcp-config mcp.yaml        # Connect to MCP servers
python3 launch.py --show-models                # Show available models
```

---

## Documentation

See the [`docs/`](docs/) folder for detailed documentation:

- [What is Agent Studio?](docs/what-is-agent-studio.md) — What this project does, key concepts, use cases
- [Architecture Overview](docs/architecture.md) — System design and data flow
- [Oversight Modes](docs/oversight.md) — CEO mode vs Supervised mode
- [Agent System](docs/agents.md) — How agents are loaded, library vs local
- [Safety & Permissions](docs/safety.md) — Tool risk, spending guards, audit
- [Extending](docs/extending.md) — Add agents, templates, MCP servers, visualizers

---

## Credits

Agent persona library from [agency-agents](https://github.com/msitarzewski/agency-agents) by [@msitarzewski](https://github.com/msitarzewski) (MIT License).
