# MCP Examples

Ready-to-use configs that connect Agent Studio to real systems.

## Quick Setup

Pick an example, copy it, and run:

```bash
# Filesystem — analyze local files
cp examples/mcp/filesystem.yaml mcp_config.yaml
# Edit the path in mcp_config.yaml
python3 launch.py --execute --env dev

# GitHub — review PRs, issues, code
export GITHUB_TOKEN=$(gh auth token)   # or paste your token
cp examples/mcp/github.yaml mcp_config.yaml
python3 launch.py --execute --env dev

# Custom — build your own
cp examples/mcp/custom.yaml mcp_config.yaml
# Uncomment the servers you want
python3 launch.py --execute --env dev
```

## Available Examples

### `filesystem.yaml`
Read and analyze local files. Works with code, docs, CSVs, configs.

Try these tasks:
- "Summarize all the Python files in this directory"
- "Read the CSV and find the top 10 customers by revenue"
- "Review all config files and flag any security issues"

### `github.yaml`
Access GitHub repos, PRs, issues, and code.

Needs a GitHub token (or `gh auth token` if you use the CLI).

Try these tasks:
- "Review all open PRs and summarize each one"
- "Find all TODO comments across the codebase"
- "List recent issues and suggest which ones to prioritize"

### `custom.yaml`
Blank starter with all common servers commented out. Uncomment what you need.

Includes: Filesystem, GitHub, PostgreSQL, SQLite, Slack, Web Fetch, Puppeteer.

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
