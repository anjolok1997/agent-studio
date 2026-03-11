"""
Engine — Manager agent orchestration.

The Engine is the top-level entry point. It breaks a goal into subtasks,
delegates to specialist workers, validates via the quality gate,
and synthesizes the final result.
"""

import os
from anthropic import Anthropic
from dotenv import load_dotenv

from .events import EventEmitter
from .station import Station, list_available_agents
from .quality_gate import QualityGate

load_dotenv()


class Engine:
    """Orchestrates specialist agents to achieve a goal."""

    def __init__(
        self,
        client: Anthropic = None,
        manager_model: str = "claude-sonnet-4-6",
        worker_model: str = "claude-haiku-4-5-20251001",
        checker_model: str = "claude-haiku-4-5-20251001",
        emitter: EventEmitter = None,
    ):
        self.client = client or Anthropic()
        self.manager_model = manager_model
        self.emitter = emitter or EventEmitter()
        self.station = Station(self.client, worker_model=worker_model, emitter=self.emitter)
        self.quality_gate = QualityGate(self.client, checker_model=checker_model, emitter=self.emitter)

    def _build_tools(self, allowed_agents: list[str] = None) -> list[dict]:
        """Build manager tools, optionally restricted to specific agents."""
        agents = allowed_agents or list_available_agents()
        return [
            {
                "name": "delegate_task",
                "description": (
                    "Delegate a focused subtask to the right specialist agent. "
                    "The specialist will complete the work and a QA agent will validate it. "
                    f"Available agent types: {agents}"
                ),
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "subtask": {
                            "type": "string",
                            "description": "Clear, self-contained description of what the specialist must deliver",
                        },
                        "agent_type": {
                            "type": "string",
                            "enum": agents,
                            "description": "Which specialist to assign this subtask to",
                        },
                    },
                    "required": ["subtask", "agent_type"],
                },
            },
        ]

    def run(self, goal: str, allowed_agents: list[str] = None) -> dict:
        """
        Run the manager agent on a goal.
        Returns {"summary": str, "artifacts": list[dict]}.
        """
        agents = allowed_agents or list_available_agents()
        tools = self._build_tools(agents)

        self.emitter.emit("engine.started", {"goal": goal, "agents": agents})

        print(f"\n{'='*60}")
        print(f"GOAL: {goal}")
        print(f"Available specialists: {agents}")
        print(f"{'='*60}\n")

        system = f"""You are an orchestrating manager agent. When given a goal:
1. Break it into 2-4 focused subtasks.
2. For each subtask, pick the right specialist from: {agents}
3. Use delegate_task to assign each subtask — work sequentially, one at a time.
4. After all workers finish, synthesize their results into a final project summary.

Choosing the right specialist matters. Pick the best fit for each subtask."""

        messages = [{"role": "user", "content": goal}]

        for iteration in range(12):
            self.emitter.emit("engine.iteration", {"iteration": iteration + 1})

            response = self.client.messages.create(
                model=self.manager_model,
                max_tokens=2048,
                system=system,
                tools=tools,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                summary = next(
                    (b.text for b in response.content if hasattr(b, "text")),
                    "(no summary)"
                )
                self.emitter.emit("engine.completed", {"iterations": iteration + 1})
                print(f"\nMANAGER DONE after {iteration + 1} iteration(s).\n")
                return {"summary": summary, "artifacts": self.station.artifacts}

            tool_results = []
            for block in response.content:
                if hasattr(block, "text") and block.text:
                    print(f"[Manager]: {block.text}")
                if block.type != "tool_use":
                    continue

                self.emitter.emit("engine.delegating", {
                    "subtask": block.input["subtask"][:80],
                    "agent_type": block.input["agent_type"],
                })

                result = self.quality_gate.validate_with_retries(
                    subtask=block.input["subtask"],
                    agent_type=block.input["agent_type"],
                    station=self.station,
                )
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

            messages.append({"role": "user", "content": tool_results})

        return {"summary": "Manager hit iteration limit.", "artifacts": self.station.artifacts}
