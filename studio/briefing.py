"""
Briefing — Interactive pre-execution conversation with the manager.

The user discusses approach with a briefing manager agent before
the team starts working. Replaces the old one-shot plan + Y/n flow.
"""

import re
from dataclasses import dataclass

from .llm import LLM
from .station import load_agent_prompt

# ─── Colors ──────────────────────────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"

# Signals that the user is ready to execute
GO_SIGNALS = re.compile(
    r"^(go|run|start|proceed|execute|do it|let'?s go|lgtm|looks good|"
    r"that works|sounds good|ship it|good to go|approved?|yes go)(\s|$|!|\.)",
    re.IGNORECASE,
)

QUIT_SIGNALS = re.compile(
    r"^(quit|exit|abort|cancel|stop|nevermind|never mind)(\s|$|!|\.)",
    re.IGNORECASE,
)

MAX_TURNS = 8


SPEED_PRESETS = {
    "fast": ("claude-sonnet-4-6", "claude-haiku-4-5-20251001"),
    "balanced": ("claude-opus-4-6", "claude-sonnet-4-6"),
    "powerful": ("claude-opus-4-6", "claude-opus-4-6"),
}


@dataclass
class BriefingResult:
    """What the briefing returns to launch.py."""
    context: str        # Formatted transcript for engine
    approved: bool      # True = user said go, False = user quit
    turns: int          # Number of conversation turns
    tokens_used: int    # Total tokens consumed during briefing
    speed_override: str = None  # "fast", "balanced", "powerful" or None


def _format_manager_message(text: str) -> str:
    """Render a manager message with a box border."""
    lines = text.strip().splitlines()
    width = min(max((len(l) for l in lines), default=40), 72)

    output = []
    output.append(f"  {CYAN}\u250c\u2500 Manager {'─' * (width - 8)}\u2510{RESET}")
    for line in lines:
        padded = line.ljust(width)
        output.append(f"  {CYAN}│{RESET} {padded} {CYAN}│{RESET}")
    output.append(f"  {CYAN}\u2514{'─' * (width + 2)}\u2518{RESET}")
    return "\n".join(output)


class Briefing:
    """Multi-turn briefing conversation with the manager agent."""

    def __init__(self, llm: LLM, agents: list[str], goal: str,
                 complexity: str = "medium",
                 connected_mcps: list[str] = None, available_mcps: dict = None,
                 claude_integrations_info: str = None):
        self.llm = llm
        self.agents = agents
        self.goal = goal
        self.complexity = complexity
        self.connected_mcps = connected_mcps or []
        self.available_mcps = available_mcps or {}
        self.claude_integrations_info = claude_integrations_info
        self.tokens_used = 0

    def _build_system(self) -> str:
        """Load the briefing-manager agent and add context."""
        base = load_agent_prompt("briefing-manager")
        agent_list = ", ".join(self.agents)

        complexity_hints = {
            "simple": (
                "This was assessed as a SIMPLE task. Keep your briefing SHORT — "
                "2-3 sentences max, no questions unless something is genuinely unclear. "
                "Just state what you'll do and tell the user to type 'go'. "
                "Do NOT over-complicate it."
            ),
            "medium": (
                "This was assessed as a MEDIUM task. Keep your briefing concise — "
                "quick take on the approach, ask at most one question if needed."
            ),
            "complex": (
                f"This was assessed as a COMPLEX task ({len(self.agents)} specialists). "
                "Take time to align on approach — propose a sequence, ask about priorities."
            ),
        }
        complexity_hint = complexity_hints.get(self.complexity, complexity_hints["medium"])

        system = (
            f"{base}\n\n"
            f"## Task Complexity\n"
            f"{complexity_hint}\n\n"
            f"## Available Specialists\n"
            f"{agent_list}\n\n"
        )

        # Tell the manager what tools are connected
        if self.connected_mcps:
            mcp_list = ", ".join(self.connected_mcps)
            system += (
                f"## Connected Tools\n"
                f"Your team currently has access to: {mcp_list}\n"
                f"Workers can use these tools during execution.\n\n"
            )

        # Tell the manager what tools COULD be connected
        not_connected = {k: v for k, v in self.available_mcps.items()
                         if k not in self.connected_mcps}
        if not_connected:
            tool_lines = "\n".join(
                f"- **{v['name']}**: {v['description']} → `studio mcp add`"
                for k, v in not_connected.items()
            )
            system += (
                f"## Tools Available (not yet connected)\n"
                f"These can be connected in 30 seconds if the task needs them:\n"
                f"{tool_lines}\n\n"
                f"If the user's goal would benefit from one of these tools, suggest it naturally.\n"
                f"Example: \"This would work better with filesystem access. "
                f"Type /mcp right here to connect it — takes 30 seconds.\"\n"
                f"Don't push — just mention it once if relevant.\n\n"
            )

        # Claude integrations (Notion, Slack, etc. already authenticated)
        if self.claude_integrations_info:
            system += (
                f"## Claude Integrations\n"
                f"{self.claude_integrations_info}\n"
                f"Workers automatically have access to connected integrations. "
                f"If the task involves one of these tools, mention it — e.g. "
                f"\"I see you have Notion connected, so I can write the study guide "
                f"directly to your Notion workspace.\"\n\n"
            )

        system += (
            f"## Rules for This Conversation\n"
            f"- Open with your take on the goal and a proposed approach.\n"
            f"- Name specific specialists and what each would deliver.\n"
            f"- Keep responses to 2-4 short paragraphs. No walls of text.\n"
            f"- When you and the user are aligned, tell them to type 'go'.\n"
        )
        return system

    def run(self) -> BriefingResult:
        """Run the briefing conversation. Returns when user says go or quit."""
        system = self._build_system()
        conversation = [f"GOAL: {self.goal}"]

        # Manager's opening message
        print(f"\n  {DIM}Manager is reviewing your goal...{RESET}\n")
        response = self.llm.call(system, "\n\n".join(conversation), max_tokens=1024)
        self.tokens_used += response.input_tokens + response.output_tokens

        manager_reply = response.text.strip()
        conversation.append(f"[Manager]: {manager_reply}")
        print(_format_manager_message(manager_reply))

        # Conversation loop
        for turn in range(1, MAX_TURNS + 1):
            if turn == MAX_TURNS:
                print(f"\n  {YELLOW}Briefing is getting long — type 'go' to start or 'quit' to abort.{RESET}")

            print(f"\n  {DIM}('go' to execute, 'quit' to abort, '/mcp' to connect a tool, '/fast' '/powerful' to change speed){RESET}")
            try:
                user_input = input(f"  {BOLD}You > {RESET}").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return BriefingResult(
                    context=self._format_context(conversation),
                    approved=False, turns=turn, tokens_used=self.tokens_used,
                )

            if not user_input:
                continue

            # /mcp — inline MCP setup, then resume conversation
            if user_input.lower() in ("/mcp", "/mcp add"):
                newly_connected = self._handle_mcp_setup()
                if newly_connected:
                    # Rebuild system prompt with new tools
                    system = self._build_system()
                    conversation.append(
                        f"[System]: Tools updated. Now connected: {', '.join(self.connected_mcps)}"
                    )
                    print(f"\n  {GREEN}Tools updated. Resuming conversation...{RESET}\n")

                    # Let the manager acknowledge the new tool
                    prompt = "\n\n".join(conversation)
                    response = self.llm.call(system, prompt, max_tokens=1024)
                    self.tokens_used += response.input_tokens + response.output_tokens
                    manager_reply = response.text.strip()
                    conversation.append(f"[Manager]: {manager_reply}")
                    print(_format_manager_message(manager_reply))
                continue

            # /fast, /balanced, /powerful — change speed
            speed_cmd = user_input.lower().lstrip("/")
            if speed_cmd in SPEED_PRESETS:
                self._speed_override = speed_cmd
                manager_model, worker_model = SPEED_PRESETS[speed_cmd]
                print(f"\n  {GREEN}Speed set to {speed_cmd}{RESET} {DIM}(manager: {manager_model.split('-')[1]}, workers: {worker_model.split('-')[1]}){RESET}")
                continue

            if GO_SIGNALS.match(user_input):
                conversation.append(f"[User]: {user_input}")
                print(f"\n  {GREEN}Briefing complete. Launching agents...{RESET}")
                return BriefingResult(
                    context=self._format_context(conversation),
                    approved=True, turns=turn, tokens_used=self.tokens_used,
                    speed_override=getattr(self, '_speed_override', None),
                )

            if QUIT_SIGNALS.match(user_input):
                return BriefingResult(
                    context="", approved=False,
                    turns=turn, tokens_used=self.tokens_used,
                )

            # Regular message — continue conversation
            conversation.append(f"[User]: {user_input}")
            prompt = "\n\n".join(conversation)

            print(f"\n  {DIM}Manager is thinking...{RESET}\n")
            response = self.llm.call(system, prompt, max_tokens=1024)
            self.tokens_used += response.input_tokens + response.output_tokens

            manager_reply = response.text.strip()
            conversation.append(f"[Manager]: {manager_reply}")
            print(_format_manager_message(manager_reply))

        # Hit max turns — auto-proceed
        print(f"\n  {YELLOW}Max briefing turns reached. Proceeding with current plan.{RESET}")
        return BriefingResult(
            context=self._format_context(conversation),
            approved=True, turns=MAX_TURNS, tokens_used=self.tokens_used,
        )

    def _handle_mcp_setup(self) -> bool:
        """Run inline MCP setup. Returns True if a new server was connected."""
        from .mcp_cli import cli_mcp_add, _load_config, DEFAULT_CONFIG_PATH

        before = set(_load_config().get("servers", {}).keys())
        cli_mcp_add()
        after = set(_load_config().get("servers", {}).keys())

        newly_added = after - before
        if newly_added:
            self.connected_mcps.extend(newly_added)
            return True
        return False

    def _format_context(self, conversation: list[str]) -> str:
        """Format the briefing transcript for the engine's manager."""
        transcript = "\n".join(conversation)
        return (
            "BRIEFING TRANSCRIPT (user discussed approach before execution):\n"
            f"{transcript}\n\n"
            "Use the decisions and preferences from this briefing to guide your delegation."
        )
