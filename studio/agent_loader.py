"""
Agent Loader — Unified agent discovery from library + local sources.

Merges agents from the agency-agents library (default) with local
agents/ directory (user overrides). Local agents take priority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


# Default paths relative to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCAL_DIR = PROJECT_ROOT / "agents"
DEFAULT_LIBRARY_DIR = PROJECT_ROOT / "lib" / "agency-agents"

# Categories to skip in the library (not agent directories)
SKIP_DIRS = {"examples", "integrations", "scripts", ".github", ".git"}

# Agent IDs to exclude from listings
EXCLUDED_AGENTS = {"reality-checker"}


@dataclass
class AgentInfo:
    """Metadata for a single agent."""
    id: str                    # Filename stem, e.g. "engineering-backend-architect"
    name: str                  # Display name from frontmatter or derived from ID
    description: str           # One-line description
    emoji: str                 # Emoji for display
    category: str              # Directory name or "custom" for local agents
    source: str                # "library" or "local"
    path: Path = field(repr=False)  # Full path to the .md file


def _parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from a markdown file. Returns {} if none."""
    text = path.read_text()
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    # Simple key: value parsing (avoids yaml dependency for this)
    fm = {}
    for line in match.group(1).strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm


def _id_from_path(path: Path) -> str:
    """Derive agent ID from file path."""
    return path.stem


def _name_from_id(agent_id: str) -> str:
    """Derive display name from agent ID when no frontmatter name exists."""
    # "engineering-backend-architect" → "Backend Architect"
    # Strip category prefix if present
    parts = agent_id.split("-")
    # Common category prefixes in agency-agents
    categories = {
        "engineering", "design", "marketing", "product", "sales",
        "academic", "strategy", "support", "testing", "specialized",
        "spatial", "paid", "project", "game",
    }
    if parts and parts[0] in categories:
        parts = parts[1:]
    # Handle two-word prefixes like "paid-media", "game-development", "project-management"
    if len(parts) > 1 and "-".join(parts[:2]) in {"media", "development", "management", "computing"}:
        parts = parts[1:]
    return " ".join(w.capitalize() for w in parts)


class AgentLoader:
    """
    Discovers and loads agents from library + local sources.

    Priority: local agents override library agents with the same ID.
    """

    def __init__(self, local_dir: Path = None, library_dir: Path = None):
        self.local_dir = local_dir or DEFAULT_LOCAL_DIR
        self.library_dir = library_dir or DEFAULT_LIBRARY_DIR
        self._agents: dict[str, AgentInfo] | None = None

    def _scan_library(self) -> dict[str, AgentInfo]:
        """Scan the agency-agents library for agents grouped by category."""
        agents = {}
        if not self.library_dir.exists():
            return agents

        for category_dir in sorted(self.library_dir.iterdir()):
            if not category_dir.is_dir() or category_dir.name in SKIP_DIRS:
                continue
            category = category_dir.name
            for md_file in sorted(category_dir.glob("*.md")):
                agent_id = _id_from_path(md_file)
                if agent_id in EXCLUDED_AGENTS:
                    continue
                fm = _parse_frontmatter(md_file)
                # Skip non-agent files (READMEs, docs without frontmatter name)
                if not fm.get("name"):
                    continue
                agents[agent_id] = AgentInfo(
                    id=agent_id,
                    name=fm.get("name", _name_from_id(agent_id)),
                    description=fm.get("description", ""),
                    emoji=fm.get("emoji", ""),
                    category=category,
                    source="library",
                    path=md_file,
                )
        return agents

    def _scan_local(self) -> dict[str, AgentInfo]:
        """Scan local agents/ directory."""
        agents = {}
        if not self.local_dir.exists():
            return agents

        for md_file in sorted(self.local_dir.glob("*.md")):
            agent_id = _id_from_path(md_file)
            if agent_id in EXCLUDED_AGENTS:
                continue
            fm = _parse_frontmatter(md_file)
            agents[agent_id] = AgentInfo(
                id=agent_id,
                name=fm.get("name", _name_from_id(agent_id)),
                description=fm.get("description", ""),
                emoji=fm.get("emoji", ""),
                category="custom",
                source="local",
                path=md_file,
            )
        return agents

    def _load(self):
        """Load and merge agents. Local overrides library."""
        if self._agents is not None:
            return
        # Library first, local overrides
        self._agents = self._scan_library()
        local = self._scan_local()
        for agent_id, info in local.items():
            if agent_id in self._agents:
                info.category = f"custom (overrides {self._agents[agent_id].category})"
            self._agents[agent_id] = info

    def list_agents(self) -> dict[str, AgentInfo]:
        """Return all agents, keyed by ID. Local overrides library."""
        self._load()
        return dict(self._agents)

    def list_categories(self) -> list[str]:
        """Return sorted unique categories."""
        self._load()
        cats = sorted(set(a.category for a in self._agents.values()))
        # Move "custom" to the end if present
        if "custom" in cats:
            cats.remove("custom")
            cats.append("custom")
        return cats

    def agents_by_category(self) -> dict[str, list[AgentInfo]]:
        """Return agents grouped by category."""
        self._load()
        grouped: dict[str, list[AgentInfo]] = {}
        for agent in self._agents.values():
            cat = agent.category.split(" (")[0]  # strip "(overrides ...)" suffix
            grouped.setdefault(cat, []).append(agent)
        # Sort within each category
        for cat in grouped:
            grouped[cat].sort(key=lambda a: a.name)
        return grouped

    def load_prompt(self, agent_id: str) -> str:
        """Load the full markdown prompt for an agent. Local takes priority."""
        self._load()
        info = self._agents.get(agent_id)
        if info:
            return info.path.read_text()
        # Fallback
        available = list(self._agents.keys())[:10]
        return (
            f"You are a helpful specialist. "
            f"(Note: agent type '{agent_id}' not found. "
            f"Available: {available}...)"
        )

    def list_agent_ids(self) -> list[str]:
        """Return sorted list of all agent IDs."""
        self._load()
        return sorted(self._agents.keys())

    def get_agent(self, agent_id: str) -> AgentInfo | None:
        """Get info for a single agent."""
        self._load()
        return self._agents.get(agent_id)

    @property
    def library_count(self) -> int:
        self._load()
        return sum(1 for a in self._agents.values() if a.source == "library")

    @property
    def local_count(self) -> int:
        self._load()
        return sum(1 for a in self._agents.values() if a.source == "local")
