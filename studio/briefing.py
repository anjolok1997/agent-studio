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


@dataclass
class BriefingResult:
    """What the briefing returns to launch.py."""
    context: str        # Formatted transcript for engine
    approved: bool      # True = user said go, False = user quit
    turns: int          # Number of conversation turns
    tokens_used: int    # Total tokens consumed during briefing


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

    def __init__(self, llm: LLM, agents: list[str], goal: str):
        self.llm = llm
        self.agents = agents
        self.goal = goal
        self.tokens_used = 0

    def _build_system(self) -> str:
        """Load the briefing-manager agent and add context."""
        base = load_agent_prompt("briefing-manager")
        agent_list = ", ".join(self.agents)
        return (
            f"{base}\n\n"
            f"## Available Specialists\n"
            f"{agent_list}\n\n"
            f"## Rules for This Conversation\n"
            f"- Open with your take on the goal and a proposed approach.\n"
            f"- Name specific specialists and what each would deliver.\n"
            f"- Keep responses to 2-4 short paragraphs. No walls of text.\n"
            f"- When you and the user are aligned, tell them to type 'go'.\n"
        )

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

            print(f"\n  {DIM}(type 'go' to execute, 'quit' to abort){RESET}")
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

            if GO_SIGNALS.match(user_input):
                conversation.append(f"[User]: {user_input}")
                print(f"\n  {GREEN}Briefing complete. Launching agents...{RESET}")
                return BriefingResult(
                    context=self._format_context(conversation),
                    approved=True, turns=turn, tokens_used=self.tokens_used,
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

    def _format_context(self, conversation: list[str]) -> str:
        """Format the briefing transcript for the engine's manager."""
        transcript = "\n".join(conversation)
        return (
            "BRIEFING TRANSCRIPT (user discussed approach before execution):\n"
            f"{transcript}\n\n"
            "Use the decisions and preferences from this briefing to guide your delegation."
        )
