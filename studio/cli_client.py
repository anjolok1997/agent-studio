"""
CLI Client — Claude CLI wrapper for sign-in-based access.

Wraps the `claude` CLI with `-p` flag to provide an interface compatible
with the Anthropic Python SDK. Uses subprocess calls with --max-turns 1
and --resume for session continuity, preserving the existing tool loop.

This allows Agent Studio to run via Claude CLI login (Pro/Max/Team)
instead of requiring an API key.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field


# JSON schema for structured tool-calling output
TOOL_CALL_SCHEMA = json.dumps({
    "type": "object",
    "properties": {
        "reasoning": {
            "type": "string",
            "description": "Your step-by-step thinking before acting",
        },
        "actions": {
            "type": "array",
            "description": "Tool calls to make. Empty array if no tools needed.",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "input": {"type": "object"},
                },
                "required": ["name", "input"],
            },
        },
        "final_text": {
            "type": "string",
            "description": "Your final response text. Only populate when you have no more tool calls to make.",
        },
    },
    "required": ["reasoning", "actions"],
})


@dataclass
class CLIUsage:
    """Token usage from a CLI call."""
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class TextBlock:
    """Mimics anthropic.types.TextBlock."""
    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    """Mimics anthropic.types.ToolUseBlock."""
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class CLIResponse:
    """Mimics anthropic.types.Message."""
    stop_reason: str = "end_turn"
    content: list = field(default_factory=list)
    usage: CLIUsage = field(default_factory=CLIUsage)
    session_id: str = ""
    cost_usd: float = 0.0


def _format_tools_for_prompt(tools: list[dict]) -> str:
    """Encode tool definitions into a system prompt appendix."""
    if not tools:
        return ""

    tool_list = []
    for tool in tools:
        name = tool["name"]
        desc = tool.get("description", "")
        schema = tool.get("input_schema", {})
        props = schema.get("properties", {})
        required = schema.get("required", [])

        params = []
        for pname, pinfo in props.items():
            ptype = pinfo.get("type", "string")
            req = " (required)" if pname in required else ""
            params.append(f"  - {pname}: {ptype}{req}")

        tool_list.append(f"- {name}: {desc}\n" + "\n".join(params))

    example = json.dumps({
        "reasoning": "I need to research this topic first",
        "actions": [{"name": tools[0]["name"], "input": {k: f"<{k}>" for k in tools[0].get("input_schema", {}).get("properties", {})}}],
    }, indent=2)

    done_example = json.dumps({
        "reasoning": "I have all the information needed",
        "actions": [],
        "final_text": "Your complete response here...",
    }, indent=2)

    return f"""

## CRITICAL INSTRUCTIONS — TOOL CALLING

You MUST respond with ONLY a valid JSON object (no markdown, no explanation outside JSON).

To call a tool:
{example}

When done (no more tools needed):
{done_example}

Available tools:
{chr(10).join(tool_list)}

IMPORTANT: Your entire response must be a single JSON object. Nothing before or after it."""


def _extract_json(text: str) -> str | None:
    """Extract JSON from text, handling code fences and surrounding text."""
    text = text.strip()

    # Try stripping code fences
    if "```" in text:
        import re
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()

    # Try parsing as-is
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # Try finding JSON object in the text
    import re
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            json.loads(match.group())
            return match.group()
        except json.JSONDecodeError:
            pass

    return None


def _parse_structured_response(result_text: str) -> CLIResponse:
    """Parse the CLI JSON result into a CLIResponse with proper content blocks."""
    json_str = _extract_json(result_text)

    if not json_str:
        # Not structured — treat as plain text
        return CLIResponse(
            stop_reason="end_turn",
            content=[TextBlock(text=result_text if result_text else "(no output)")],
        )

    data = json.loads(json_str)
    actions = data.get("actions", [])
    reasoning = data.get("reasoning", "")
    final_text = data.get("final_text", "")

    content = []

    # Add reasoning as text if present
    if reasoning:
        content.append(TextBlock(text=reasoning))

    if actions:
        # Has tool calls
        for action in actions:
            content.append(ToolUseBlock(
                id=f"cli_{uuid.uuid4().hex[:12]}",
                name=action["name"],
                input=action.get("input", {}),
            ))
        return CLIResponse(stop_reason="tool_use", content=content)
    else:
        # No tool calls — end turn
        if final_text:
            content = [TextBlock(text=final_text)]
        elif not content:
            content = [TextBlock(text=result_text)]
        return CLIResponse(stop_reason="end_turn", content=content)


class CLIMessages:
    """Mimics anthropic.Anthropic().messages with CLI subprocess calls."""

    def __init__(self):
        self._session_id: str | None = None

    def reset_session(self):
        """Start a new conversation session."""
        self._session_id = None

    def create(
        self,
        model: str,
        max_tokens: int,
        system: str,
        messages: list,
        tools: list | None = None,
    ) -> CLIResponse:
        """
        Make a single LLM call via claude CLI.

        Mimics anthropic.messages.create() interface.
        Uses --max-turns 1 to get exactly one response,
        then returns so the caller can execute tools locally.
        """
        # Build the prompt from the last user message
        prompt = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    prompt = content
                elif isinstance(content, list):
                    # Handle tool_result blocks
                    parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "tool_result":
                                parts.append(f"[Tool Result for {block.get('tool_use_id', 'unknown')}]: {block.get('content', '')}")
                            elif block.get("type") == "text":
                                parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            parts.append(block)
                    prompt = "\n".join(parts)
                break

        if not prompt:
            prompt = "Continue."

        # Build system prompt with tool definitions
        full_system = system
        if tools:
            full_system += _format_tools_for_prompt(tools)

        # Map model shorthand to CLI model names
        model_map = {
            "claude-haiku-4-5-20251001": "haiku",
            "claude-sonnet-4-6": "sonnet",
            "claude-opus-4-6": "opus",
        }
        cli_model = model_map.get(model, model)

        # Build command
        cmd = [
            "claude",
            "-p", prompt,
            "--output-format", "json",
            "--max-turns", "1",
            "--model", cli_model,
            "--system-prompt", full_system,
        ]

        # Resume session if we have one
        if self._session_id:
            cmd.extend(["--resume", self._session_id])

        # Disable all built-in CLI tools so the model only sees our custom tools
        # encoded in the system prompt. --tools "" removes Read/Edit/Bash/etc.
        cmd.extend(["--tools", ""])

        # Run subprocess — clear API key env vars so CLI uses its own auth
        import os
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return CLIResponse(
                stop_reason="end_turn",
                content=[TextBlock(text="[ERROR] CLI call timed out after 120 seconds.")],
            )
        except FileNotFoundError:
            raise RuntimeError(
                "Claude CLI not found. Install it or use --api-key mode.\n"
                "Install: npm install -g @anthropic-ai/claude-code"
            )

        # Parse the CLI JSON response
        try:
            cli_output = json.loads(result.stdout)
        except json.JSONDecodeError:
            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip() or "Unknown CLI error"
                return CLIResponse(
                    stop_reason="end_turn",
                    content=[TextBlock(text=f"[CLI ERROR] {error_msg}")],
                )
            return CLIResponse(
                stop_reason="end_turn",
                content=[TextBlock(text=result.stdout.strip() or "(empty response)")],
            )

        # Check for CLI-level errors
        if cli_output.get("is_error"):
            error_msg = cli_output.get("result", "Unknown CLI error")
            return CLIResponse(
                stop_reason="end_turn",
                content=[TextBlock(text=f"[CLI ERROR] {error_msg}")],
            )

        # Extract session ID for future --resume calls
        self._session_id = cli_output.get("session_id", self._session_id)

        # Extract usage
        usage = CLIUsage()
        raw_usage = cli_output.get("usage", {})
        usage.input_tokens = raw_usage.get("input_tokens", 0)
        usage.output_tokens = raw_usage.get("output_tokens", 0)

        # Parse the result text
        result_text = cli_output.get("result", "")
        cost_usd = cli_output.get("total_cost_usd", 0.0)

        if tools:
            # Expect structured JSON output from --json-schema
            response = _parse_structured_response(result_text)
        else:
            # Simple text response (Planner, QualityGate)
            response = CLIResponse(
                stop_reason="end_turn",
                content=[TextBlock(text=result_text)],
            )

        response.usage = usage
        response.session_id = self._session_id or ""
        response.cost_usd = cost_usd

        return response


class CLIClient:
    """
    Drop-in replacement for anthropic.Anthropic() that uses the claude CLI.

    Requires the user to be logged in via `claude login`.
    Works with Claude CLI login — no API key needed.
    """

    def __init__(self):
        self.messages = CLIMessages()

        # Verify CLI is available
        if not shutil.which("claude"):
            raise RuntimeError(
                "Claude CLI not found. Please install it:\n"
                "  npm install -g @anthropic-ai/claude-code\n\n"
                "Or use API key mode:\n"
                "  python3 launch.py --api-key"
            )

    def new_session(self) -> CLIMessages:
        """Create a new messages interface with a fresh session.

        Use this when you need isolated conversations (e.g., per worker).
        """
        return CLIMessages()


def check_cli_login() -> bool:
    """Check if the user is logged into the claude CLI."""
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
