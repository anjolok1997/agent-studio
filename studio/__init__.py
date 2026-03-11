"""
Agent Studio — A multi-agent orchestration framework.

Assemble specialist AI agents into teams, pick a template, and let them work.
"""

__version__ = "0.3.0"

from .engine import Engine
from .station import Station, list_available_agents, load_agent_prompt
from .quality_gate import QualityGate
from .events import EventEmitter, Event
from .permissions import PermissionGuard, ExecutionMode, SpendingGuard
from .audit import AuditLog

try:
    from .mcp_bridge import MCPBridge
except ImportError:
    MCPBridge = None
