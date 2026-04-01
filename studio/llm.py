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


class LLM:
    """
    Unified LLM interface. Just call(system, prompt) -> text.

    Usage:
        llm = LLM()                    # Auto-detects: CLI or API key
        llm = LLM(provider="cli")      # Force Claude CLI
        llm = LLM(provider="api")      # Force Anthropic SDK
    """

    def __init__(self, provider: str = "auto", model: str = "claude-haiku-4-5-20251001",
                 mcp_config_path: str = None):
        self.model = model
        self.provider = self._resolve_provider(provider)
        self.mcp_config_path = mcp_config_path

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

        # If MCP config exists, let the CLI handle tool calling
        if self.mcp_config_path and os.path.exists(self.mcp_config_path):
            cmd.extend(["--mcp-config", str(self.mcp_config_path)])
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
