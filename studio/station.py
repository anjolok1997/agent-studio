"""
Station — Worker agent execution.

Each worker is a specialist agent that runs a focused subtask.
Uses LLM.call() — no SDK-specific interfaces.
When MCP tools are available, workers can call them during execution.
"""

from .llm import LLM
from .events import EventEmitter
from .permissions import PermissionGuard
from .agent_loader import AgentLoader


# Shared loader instance
_default_loader: AgentLoader = None


def _get_loader() -> AgentLoader:
    global _default_loader
    if _default_loader is None:
        _default_loader = AgentLoader()
    return _default_loader


def load_agent_prompt(agent_type: str) -> str:
    """Load a specialist system prompt by agent ID."""
    return _get_loader().load_prompt(agent_type)


def list_available_agents() -> list[str]:
    """Return all available agent IDs (library + local)."""
    return _get_loader().list_agent_ids()


def get_agent_loader() -> AgentLoader:
    """Get the shared AgentLoader instance."""
    return _get_loader()


class Station:
    """Runs a specialist worker agent on a single subtask."""

    def __init__(self, llm: LLM = None, emitter: EventEmitter = None,
                 permissions: PermissionGuard = None, mcp_bridge=None):
        self.llm = llm or LLM()
        self.emitter = emitter or EventEmitter()
        self.permissions = permissions or PermissionGuard()
        self.mcp_bridge = mcp_bridge
        self.artifacts: list[dict] = []
        self.last_input_tokens: int = 0
        self.last_output_tokens: int = 0

    def _do_research(self, topic: str, agent_type: str) -> str:
        """Actually research a topic using the model's knowledge."""
        system = load_agent_prompt(agent_type)
        prompt = (
            f"Research the following topic thoroughly and provide your findings. "
            f"Be specific, detailed, and practical. Use your expertise.\n\n"
            f"Topic: {topic}\n\n"
            f"Provide structured, actionable content. Include specifics: "
            f"tools, patterns, best practices, trade-offs, and concrete "
            f"recommendations where relevant."
        )

        response = self.llm.call(system, prompt, max_tokens=2048)
        print(f"      [{agent_type}] research -> {len(response.text)} chars")
        return response.text

    def run(self, subtask: str, agent_type: str, attempt: int = 1, prior_feedback: str = "") -> str:
        """Run a specialist worker on a subtask. Returns the worker's final text."""
        system = load_agent_prompt(agent_type)
        self.emitter.emit("worker.started", {"agent": agent_type, "subtask": subtask, "attempt": attempt})

        prompt = subtask
        if prior_feedback:
            prompt = (
                f"{subtask}\n\n"
                f"[Attempt {attempt}/{2} — Previous attempt was rejected]\n"
                f"QA Feedback: {prior_feedback}\n"
                f"Please address the feedback and try again."
            )

        prompt += (
            "\n\nRULES:\n"
            "- Do what was asked, nothing more. Do not add features or make improvements beyond the task.\n"
            "- If you don't know something, say so. Do not guess or make up information.\n"
            "- If you need access to a system or file you don't have, say what's missing.\n"
            "- Do not fabricate data, file contents, API responses, or statistics.\n"
            "- Use connected tools for real data when available — do not generate from memory if a tool can provide it.\n"
            "- Produce your complete deliverable directly. Be thorough and specific."
        )

        # Detect what kind of output the task needs and instruct accordingly
        task_lower = subtask.lower()

        code_keywords = ["code", "build", "implement", "api", "app", "script",
                         "database", "schema", "deploy", "docker", "config", "pipeline"]
        doc_keywords = ["guide", "document", "report", "summary", "plan", "analysis",
                        "write", "draft", "create", "produce", "cheat sheet", "reference",
                        "blog", "article", "proposal", "spec", "documentation"]

        if any(kw in task_lower for kw in code_keywords):
            prompt += (
                "\n\nProduce real, runnable files. Use this format for EACH file:\n\n"
                "FILE: path/to/filename.ext\n"
                "```language\n"
                "file content here\n"
                "```\n\n"
                "Use proper relative paths. Include ALL files needed to run the project."
            )
        elif any(kw in task_lower for kw in doc_keywords):
            # Check if user specifically asked for PDF
            wants_pdf = any(kw in task_lower for kw in ["pdf", "printable", "formatted document"])
            format_note = " A PDF version will be auto-generated." if wants_pdf else ""

            prompt += (
                "\n\nProduce your output as a real file. Use this format:\n\n"
                "FILE: descriptive-filename.md\n"
                "```markdown\n"
                "your complete document here\n"
                "```\n\n"
                "Use a descriptive filename (e.g. aws-study-guide.md, api-spec.md). "
                "The content should be complete and well-structured — this becomes "
                f"a real file the user keeps.{format_note}\n"
                "Use proper markdown formatting (headings, bullets, code blocks) "
                "so the document looks professional."
            )

        # Check for MCP tools (API provider gets a tool-calling loop)
        mcp_tools = []
        if self.mcp_bridge and self.llm.provider == "api":
            mcp_tools = self.mcp_bridge.discover_tools()

        self.last_input_tokens = 0
        self.last_output_tokens = 0

        if mcp_tools:
            result = self._run_with_tools(system, prompt, mcp_tools, agent_type)
        else:
            # CLI provider handles MCP natively via --mcp-config
            response = self.llm.call(system, prompt, max_tokens=4096)
            self.last_input_tokens += response.input_tokens
            self.last_output_tokens += response.output_tokens
            result = response.text

            # If the result looks like it needs research, do it
            if len(result) < 200 and ("research" in result.lower() or "investigate" in result.lower()):
                research = self._do_research(subtask, agent_type)
                prompt_with_research = (
                    f"{prompt}\n\n"
                    f"RESEARCH FINDINGS:\n{research[:3000]}\n\n"
                    f"Now produce your final deliverable based on these findings."
                )
                response = self.llm.call(system, prompt_with_research, max_tokens=4096)
                self.last_input_tokens += response.input_tokens
                self.last_output_tokens += response.output_tokens
                result = response.text

        # Check for draft artifacts in the output
        if len(result) > 500:
            self.artifacts.append({"agent": agent_type, "content": result})
            self.emitter.emit("worker.tool_called", {
                "agent": agent_type, "tool": "draft_output", "chars": len(result),
            })

        self.emitter.emit("worker.completed", {"agent": agent_type, "chars": len(result)})
        return result

    def _run_with_tools(self, system: str, prompt: str, tools: list,
                        agent_type: str, max_rounds: int = 5) -> str:
        """Run a worker with MCP tool access via Anthropic API tool calling."""
        messages = [{"role": "user", "content": prompt}]

        for _ in range(max_rounds):
            response = self.llm.call(
                system, prompt, max_tokens=4096,
                tools=tools, messages=messages,
            )
            self.last_input_tokens += response.input_tokens
            self.last_output_tokens += response.output_tokens

            if not response.tool_calls or response.stop_reason != "tool_use":
                return response.text or "(no output)"

            # Build assistant message with the model's response
            assistant_content = []
            if response.text:
                assistant_content.append({"type": "text", "text": response.text})
            for tc in response.tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["input"],
                })
            messages.append({"role": "assistant", "content": assistant_content})

            # Execute each tool call via MCPBridge
            tool_results = []
            for tc in response.tool_calls:
                self.emitter.emit("worker.tool_called", {
                    "agent": agent_type, "tool": tc["name"], "mcp": True,
                })
                result = self.mcp_bridge.call_tool(tc["name"], tc["input"], agent_type)
                print(f"      [{agent_type}] mcp:{tc['name']} -> {len(result)} chars")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": result,
                })
            messages.append({"role": "user", "content": tool_results})

        # Hit max rounds — return whatever we have
        return response.text or "(max tool rounds reached)"
