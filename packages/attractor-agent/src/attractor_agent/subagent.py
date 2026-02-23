"""Subagent support for task decomposition and parallel work."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from attractor_agent.session import Session, SessionConfig, SessionState
from attractor_llm.types import ToolDefinition


@dataclass
class SubAgentResult:
    output: str = ""
    success: bool = False
    turns_used: int = 0


@dataclass
class SubAgentHandle:
    id: str = ""
    session: Session | None = None
    status: str = "running"  # running | completed | failed
    result: SubAgentResult | None = None


class SubAgentManager:
    """Manages subagent lifecycle for a parent session."""

    def __init__(self, parent_session: Session) -> None:
        self._parent = parent_session
        self._agents: dict[str, SubAgentHandle] = {}

    @property
    def current_depth(self) -> int:
        """Track nesting depth via parent chain."""
        depth = 0
        session = self._parent
        while hasattr(session, '_parent_session') and session._parent_session is not None:
            depth += 1
            session = session._parent_session
        return depth

    async def spawn(
        self,
        task: str,
        working_dir: str | None = None,
        model: str | None = None,
        max_turns: int = 0,
    ) -> str:
        """Spawn a subagent. Returns the agent ID."""
        max_depth = self._parent.config.max_subagent_depth
        if self.current_depth >= max_depth:
            raise RuntimeError(
                f"Maximum subagent depth ({max_depth}) exceeded"
            )

        agent_id = str(uuid.uuid4())[:8]

        # Create child session sharing parent's environment and profile
        profile = self._parent.profile
        if model:
            # Clone profile with different model
            from dataclasses import replace
            profile = replace(profile, model=model)

        config = SessionConfig(max_turns=max_turns)
        child = Session(
            profile=profile,
            llm_client=self._parent.llm_client,
            execution_env=self._parent.execution_env,
            config=config,
        )
        child._parent_session = self._parent  # type: ignore[attr-defined]

        handle = SubAgentHandle(id=agent_id, session=child, status="running")
        self._agents[agent_id] = handle

        # Submit the task
        try:
            await child.submit(task)
            handle.status = "completed"
            # Extract final text from last assistant turn
            from attractor_agent.session import AssistantTurn
            output = ""
            for turn in reversed(child.history):
                if isinstance(turn, AssistantTurn) and turn.content:
                    output = turn.content
                    break
            handle.result = SubAgentResult(
                output=output,
                success=True,
                turns_used=child._total_turns,
            )
        except Exception as e:
            handle.status = "failed"
            handle.result = SubAgentResult(
                output=str(e), success=False, turns_used=child._total_turns
            )

        return agent_id

    async def send_input(self, agent_id: str, message: str) -> str:
        """Send a message to a running subagent."""
        handle = self._agents.get(agent_id)
        if not handle:
            return f"Unknown agent: {agent_id}"
        if handle.status != "running":
            return f"Agent {agent_id} is {handle.status}"
        if handle.session:
            await handle.session.submit(message)
        return "Message sent"

    async def wait(self, agent_id: str) -> SubAgentResult:
        """Wait for a subagent to complete."""
        handle = self._agents.get(agent_id)
        if not handle:
            return SubAgentResult(output=f"Unknown agent: {agent_id}", success=False)
        if handle.result:
            return handle.result
        return SubAgentResult(output="Agent still running", success=False)

    async def close(self, agent_id: str) -> str:
        """Terminate a subagent."""
        handle = self._agents.get(agent_id)
        if not handle:
            return f"Unknown agent: {agent_id}"
        if handle.session:
            handle.session.close()
        handle.status = "completed"
        return f"Agent {agent_id} closed"

    def get(self, agent_id: str) -> SubAgentHandle | None:
        return self._agents.get(agent_id)


def make_subagent_tools(manager: SubAgentManager) -> list[ToolDefinition]:
    """Create subagent tool definitions."""

    async def spawn_agent(
        task: str,
        working_dir: str | None = None,
        model: str | None = None,
        max_turns: int = 0,
    ) -> str:
        try:
            agent_id = await manager.spawn(task, working_dir, model, max_turns)
            return f"Spawned agent {agent_id}"
        except RuntimeError as e:
            return f"Error: {e}"

    async def send_input(agent_id: str, message: str) -> str:
        return await manager.send_input(agent_id, message)

    async def wait(agent_id: str) -> str:
        result = await manager.wait(agent_id)
        return f"Output: {result.output}\nSuccess: {result.success}\nTurns: {result.turns_used}"

    async def close_agent(agent_id: str) -> str:
        return await manager.close(agent_id)

    return [
        ToolDefinition(
            name="spawn_agent",
            description="Spawn a subagent to handle a scoped task autonomously.",
            parameters={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "Task description"},
                    "working_dir": {"type": "string", "description": "Subdirectory scope"},
                    "model": {"type": "string", "description": "Model override"},
                    "max_turns": {"type": "integer", "description": "Turn limit", "default": 0},
                },
                "required": ["task"],
            },
            execute=spawn_agent,
        ),
        ToolDefinition(
            name="send_input",
            description="Send a message to a running subagent.",
            parameters={
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["agent_id", "message"],
            },
            execute=send_input,
        ),
        ToolDefinition(
            name="wait",
            description="Wait for a subagent to complete.",
            parameters={
                "type": "object",
                "properties": {"agent_id": {"type": "string"}},
                "required": ["agent_id"],
            },
            execute=wait,
        ),
        ToolDefinition(
            name="close_agent",
            description="Terminate a subagent.",
            parameters={
                "type": "object",
                "properties": {"agent_id": {"type": "string"}},
                "required": ["agent_id"],
            },
            execute=close_agent,
        ),
    ]
