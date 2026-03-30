"""
Agent Studio — A multi-agent orchestration framework.

Assemble specialist AI agents into teams, pick a template, and let them work.
"""

__version__ = "0.4.0"

from .engine import Engine
from .station import Station, list_available_agents, load_agent_prompt, get_agent_loader
from .agent_loader import AgentLoader, AgentInfo
from .cli_client import CLIClient
from .quality_gate import QualityGate
from .events import EventEmitter, Event
from .permissions import PermissionGuard, ExecutionMode, SpendingGuard, OversightMode, EscalationReason
from .audit import AuditLog
from .planner import Planner

try:
    from .mcp_bridge import MCPBridge
except ImportError:
    MCPBridge = None
