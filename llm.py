"""
LLM — Simple interface for calling language models.

Provides a unified call() function that works with:
- Claude CLI (subscription, default)
- Anthropic SDK (API key)
- Any future provider

Every component in Agent Studio uses this instead of
calling the Anthropic SDK or CLI directly.
"""

from __future__ import annotations

import json
import os
import subprocess
import shutil
from dataclasses import dataclass, field


@dataclass
class LLMResponse:
    """Simple response from an LLM call."""
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: list = field(default_factory=list)  # [{"id", "name", "input"}]
    stop_reason: str = "end_turn"


CONTEXT_LIMITS = {
    "claude-haiku-4-5-20251001": 200_000,
    "claude-sonnet-4-6": 200_000,
    "claude-opus-4-6": 200_000,
    "haiku": 200_000,
    "sonnet": 200_000,
    "opus": 200_000,
}

# Leave headroom for the response — don't fill 100% of the context
CONTEXT_SAFETY_MARGIN = 0.85


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return len(text) // 4


class LLM:
    """
    Unified LLM interface. Just call(system, prompt) -> text.

    Usage:
        llm = LLM()                    # Auto-detects: CLI or API key
        llm = LLM(provider="cli")      # Force Claude CLI
        llm = LLM(provider="api")      # Force Anthropic SDK
    """

    def __init__(self, provider: str = "auto", model: str = "claude-haiku-4-5-20251001",
                 mcp_config_path: str = None, use_claude_integrations: bool = False):
        self.model = model
        self.provider = self._resolve_provider(provider)
        self.mcp_config_path = mcp_config_path
        self.use_claude_integrations = use_claude_integrations

        if self.provider == "api":
            from anthropic import Anthropic
            self._client = Anthropic()

    def _resolve_provider(self, provider: str) -> str:
        if provider != "auto":
            return provider
        # Auto-detect: prefer CLI (subscription), fall back to API key
        if shutil.which("claude"):
            return "cli"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "api"
        raise RuntimeError(
            "No LLM provider found.\n"
            "  Install Claude CLI: npm install -g @anthropic-ai/claude-code && claude login\n"
            "  Or set ANTHROPIC_API_KEY in .env"
        )

    def call(self, system: str, prompt: str, max_tokens: int = 2048,
             tools: list = None, messages: list = None) -> LLMResponse:
        """Call the LLM. Pass tools for MCP tool-calling support."""
        # Context window validation — warn and truncate if too large
        context_limit = CONTEXT_LIMITS.get(self.model, 200_000)
        safe_limit = int(context_limit * CONTEXT_SAFETY_MARGIN)
        input_estimate = estimate_tokens(system) + estimate_tokens(prompt)

        if input_estimate > safe_limit:
            overage = input_estimate - safe_limit
            # Truncate the prompt (not system) to fit
            chars_to_trim = overage * 4
            original_len = len(prompt)
            prompt = prompt[:len(prompt) - chars_to_trim]
            import sys
            print(f"\n  \033[33m⚠ Input too large (~{input_estimate:,} tokens, limit ~{safe_limit:,}). "
                  f"Trimmed prompt from {original_len:,} to {len(prompt):,} chars.\033[0m",
                  file=sys.stderr)
        elif input_estimate > safe_limit * 0.9:
            import sys
            print(f"\n  \033[2m⚠ Input approaching context limit (~{input_estimate:,} / ~{safe_limit:,} tokens)\033[0m",
                  file=sys.stderr)

        if self.provider == "cli":
            return self._call_cli(system, prompt, max_tokens)
        else:
            return self._call_api(system, prompt, max_tokens, tools=tools, messages=messages)

    def _call_cli(self, system: str, prompt: str, max_tokens: int) -> LLMResponse:
        """Call via claude CLI. MCP tools are handled natively by the CLI."""
        # Map full model IDs to CLI shorthand
        model_map = {
            "claude-haiku-4-5-20251001": "haiku",
            "claude-sonnet-4-6": "sonnet",
            "claude-opus-4-6": "opus",
        }
        cli_model = model_map.get(self.model, self.model)

        cmd = [
            "claude", "-p", prompt,
            "--output-format", "json",
            "--model", cli_model,
            "--system-prompt", system,
        ]

        # Tool access for workers:
        # 1. Local MCP config → pass it to CLI
        # 2. Use Claude integrations → let CLI use whatever the user has connected
        # 3. No tools → disable everything (fastest, cheapest)
        if self.mcp_config_path and os.path.exists(self.mcp_config_path):
            cmd.extend(["--mcp-config", str(self.mcp_config_path)])
            cmd.extend(["--max-turns", "5"])
        elif self.use_claude_integrations:
            # Let workers use Notion, Slack, etc. that the user
            # already connected to their Claude account
            cmd.extend(["--max-turns", "5"])
        else:
            cmd.extend(["--max-turns", "1"])
            cmd.extend(["--tools", ""])

        # Clear API key so CLI uses its own auth
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return LLMResponse(text="[ERROR] Request timed out after 5 minutes.")
        except FileNotFoundError:
            raise RuntimeError("Claude CLI not found. Install: npm install -g @anthropic-ai/claude-code")

        # Parse CLI JSON response
        try:
            cli_output = json.loads(result.stdout)
        except json.JSONDecodeError:
            return LLMResponse(text=result.stdout.strip() or "(empty response)")

        if cli_output.get("is_error"):
            return LLMResponse(text=f"[ERROR] {cli_output.get('result', 'Unknown error')}")

        usage = cli_output.get("usage", {})
        return LLMResponse(
            text=cli_output.get("result", ""),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )

    def _call_api(self, system: str, prompt: str, max_tokens: int,
                  tools: list = None, messages: list = None) -> LLMResponse:
        """Call via Anthropic SDK. Supports native tool calling."""
        if messages is None:
            messages = [{"role": "user", "content": prompt}]

        kwargs = dict(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        if tools:
            kwargs["tools"] = tools

        response = self._client.messages.create(**kwargs)

        text_parts = []
        tool_calls = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else "",
            input_tokens=response.usage.input_tokens if hasattr(response, "usage") else 0,
            output_tokens=response.usage.output_tokens if hasattr(response, "usage") else 0,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
        )
