# MCP Examples

Ready-to-use configs that connect Agent Studio to real systems.

## Quick Setup

Pick an example, copy it, and run:

```bash
# Option 1: Interactive setup (recommended)
studio mcp add

# Option 2: Copy an example config
cp examples/mcp/github.yaml mcp_config.yaml
# Edit tokens/credentials in the file
studio --execute --env dev
```

### Popular setups

```bash
# GitHub — review PRs, issues, code
export GITHUB_TOKEN=$(gh auth token)
studio mcp add    # pick "GitHub"

# Slack — channel summaries, message search
studio mcp add    # pick "Slack", paste bot token

# Notion — search docs, update pages
studio mcp add    # pick "Notion", paste integration token

# Postgres — query your database
studio mcp add    # pick "PostgreSQL", paste connection string
```

## Available Examples

### `filesystem.yaml`
Read and analyze local files. Works with code, docs, CSVs, configs.

### `github.yaml`
Access GitHub repos, PRs, issues, and code. Needs a GitHub token.

### `slack.yaml`
Read channels, search messages, send updates. Needs a Slack bot token.

### `notion.yaml`
Search, read, and update Notion pages and databases. Needs an integration token.

### `postgres.yaml`
Query and inspect your PostgreSQL database (read-only by default).

### `linear.yaml`
Manage issues, projects, and cycles in Linear.

### `custom.yaml`
Blank starter with common servers commented out. Uncomment what you need.

Or use the interactive setup: `studio mcp add`

## Combining Servers

You can use multiple servers in one config:

```yaml
servers:
  filesystem:
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "./data"]

  github:
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_TOKEN: "ghp_..."
```

Agents see all tools from all connected servers and can use them together.

## Finding More MCP Servers

- [Official MCP Servers](https://github.com/modelcontextprotocol/servers)
- [MCP Directory](https://mcp.so)

## Tool Risk Levels

Each tool is automatically classified by risk based on its name:

| Pattern | Risk | What happens |
|---|---|---|
| read, list, search, get | Safe | Always allowed |
| write, create, update, send | Sensitive | Auto-approved in CEO mode (except prod) |
| delete, drop, execute, run, deploy | Dangerous | Always requires your approval |

Override in your config with `tool_risks` if the auto-detection is wrong.
