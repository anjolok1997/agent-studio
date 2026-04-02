"""
Integrations — Detect Claude's connected MCP integrations.

Runs `claude mcp list` to discover what the user has already
authenticated. Workers can use these without any extra setup.
"""

from __future__ import annotations

import subprocess
import re


def detect_claude_integrations() -> dict[str, bool]:
    """Detect which Claude integrations are connected.

    Returns {"Notion": True, "Slack": True, "Linear": False, ...}
    """
    try:
        result = subprocess.run(
            ["claude", "mcp", "list"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}

    integrations = {}
    for line in result.stdout.splitlines():
        # Parse lines like: "claude.ai Notion: https://... - ✓ Connected"
        match = re.match(r"claude\.ai\s+(.+?):\s+https?://.+?-\s+(.+)", line)
        if match:
            name = match.group(1).strip()
            status = match.group(2).strip()
            integrations[name] = "Connected" in status

    return integrations


def get_connected_names() -> list[str]:
    """Return just the names of connected integrations."""
    return [name for name, connected in detect_claude_integrations().items() if connected]


def format_for_briefing(integrations: dict[str, bool]) -> str:
    """Format integrations info for the briefing manager's system prompt."""
    connected = [name for name, ok in integrations.items() if ok]
    available = [name for name, ok in integrations.items() if not ok]

    parts = []
    if connected:
        parts.append(
            f"The user has these Claude integrations connected (workers can use them): "
            f"{', '.join(connected)}"
        )
    if available:
        parts.append(
            f"These are available but not yet authenticated: {', '.join(available)}. "
            f"The user can connect them at claude.ai/settings."
        )
    return "\n".join(parts)
