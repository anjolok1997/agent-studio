# Agent System

Agent Studio uses a two-tier agent system: a **library** of 147 pre-built agents from [agency-agents](https://github.com/msitarzewski/agency-agents), plus a **local directory** for your own custom agents.

---

## How Agents Are Loaded

The `AgentLoader` (`studio/agent_loader.py`) merges both sources at startup:

```
lib/agency-agents/         <-- Library (default agents)
  engineering/
    engineering-backend-architect.md
    engineering-sre.md
    ...
  design/
    design-ux-architect.md
    ...
  marketing/
    ...

agents/                    <-- Local (your custom agents)
  backend-architect.md
  my-specialist.md
  ...
```

**Priority: local overrides library.** If `agents/engineering-backend-architect.md` exists, it replaces the library version.

### Agent ID

Each agent's ID is its filename without the `.md` extension:

- `lib/agency-agents/engineering/engineering-backend-architect.md` -> ID: `engineering-backend-architect`
- `agents/backend-architect.md` -> ID: `backend-architect`

### Agent Prompt

The entire `.md` file content becomes the worker's system prompt. No transformation is applied — the markdown is sent directly to Claude.

---

## Library Agents

The library comes from the [agency-agents](https://github.com/msitarzewski/agency-agents) repository (MIT License), included as a git submodule at `lib/agency-agents/`.

### Categories

| Category | Count | Description |
|---|---|---|
| academic | 5 | Anthropologist, Geographer, Historian, Narratologist, Psychologist |
| design | 8 | UX Architect, UI Designer, Brand Guardian, Image Prompt Engineer |
| engineering | 26 | Backend, Frontend, DevOps, SRE, Security, Mobile, and more |
| game-development | 5 | Narrative, Level Design, Game AI |
| marketing | 29 | SEO, Content, Social, Email, Brand Voice |
| paid-media | 7 | PPC, Display, Social Ads |
| product | 5 | Product Manager, Sprint Prioritizer, Trend Researcher |
| project-management | 6 | Agile Coach, Risk Analyst |
| sales | 8 | Account Strategy, Outreach, Pipeline |
| spatial-computing | 6 | AR/VR, 3D, Spatial UI |
| specialized | 28 | Legal, Financial, Healthcare, Grant Writing, and more |
| strategy | 6 | Business Strategy, Competitive Analysis |
| support | 6 | Customer Success, Technical Support |
| testing | 8 | QA, Performance, Accessibility, Security Testing |

### Library Agent Format

Library agents use YAML frontmatter + markdown:

```markdown
---
name: Backend Architect
description: Senior backend architect specializing in scalable system design...
color: blue
emoji: <building emoji>
vibe: Designs the systems that hold everything up.
---

# Backend Architect Agent Personality

You are **Backend Architect**, a senior backend architect who...

## Your Core Mission
...

## Critical Rules You Must Follow
...
```

The frontmatter fields (`name`, `description`, `emoji`) are used for the agent menu display. The full content (frontmatter + body) is the system prompt.

### Updating the Library

The library is a git submodule. To pull the latest agents:

```bash
git submodule update --remote lib/agency-agents
```

---

## Local Agents

Your custom agents live in `agents/`. They're discovered automatically and appear under the "custom" category in the menu.

### Local Agent Format

Local agents use a simpler format (no frontmatter required):

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

You can also use the library format with YAML frontmatter if you want your agent to show a name, description, and emoji in the menu.

### Built-in Local Agents

Agent Studio ships with 12 local agents for common tasks:

| Agent | Best For |
|---|---|
| `ai-engineer` | ML models, LLM pipelines, RAG, embeddings |
| `analyst` | Data analysis, KPIs, business cases |
| `backend-architect` | APIs, databases, system design |
| `code-reviewer` | Security review, performance, quality |
| `data-engineer` | Pipelines, Airflow, dbt, Spark |
| `data-quality` | dbt tests, data contracts, anomaly detection |
| `educator` | Study guides, learning materials |
| `project-manager` | Planning, milestones, risk |
| `researcher` | Literature review, comparisons |
| `summarizer` | Document summaries, key-point extraction |
| `ux-designer` | User flows, wireframes, accessibility |
| `writer` | Blog posts, docs, proposals |

### Overriding a Library Agent

To customize a library agent, copy it to `agents/` with the same filename:

```bash
cp lib/agency-agents/engineering/engineering-sre.md agents/engineering-sre.md
# Edit agents/engineering-sre.md with your changes
```

Your local version will be used instead of the library version.

---

## Using Agents in Templates

Templates reference agents by their ID in the `agents` field:

```yaml
name: "Infrastructure Review"
description: "Review cloud infrastructure"
agents:
  - engineering-backend-architect
  - engineering-sre
  - engineering-security-engineer
goal: >
  Review the infrastructure for security, reliability, and cost.
```

You can mix library and local agents in the same template.

---

## Programmatic Access

```python
from studio.agent_loader import AgentLoader

loader = AgentLoader()

# List all agents
agents = loader.list_agents()  # dict[str, AgentInfo]

# Browse by category
by_cat = loader.agents_by_category()  # dict[str, list[AgentInfo]]

# Load a prompt
prompt = loader.load_prompt("engineering-sre")

# Get agent info
info = loader.get_agent("engineering-backend-architect")
print(info.name, info.emoji, info.category, info.source)
```
