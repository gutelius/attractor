"""Agent session and core agentic loop."""

from __future__ import annotations

import asyncio
import inspect
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from attractor_agent.events import (
    EventEmitter,
    EventKind,
    FollowUpQueue,
    SessionEvent,
    SteeringQueue,
    _tool_call_signature,
    detect_loop,
)
from attractor_agent.profiles.base import BaseProfile
from attractor_agent.tools.registry import ToolRegistry
from attractor_agent.tools.truncation import truncate_output
from attractor_llm.types import (
    Message,
    Request,
    Response,
    ToolCall,
    ToolResult,
    Usage,
)


class SessionState(str, Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    AWAITING_INPUT = "awaiting_input"
    CLOSED = "closed"


@dataclass
class SessionConfig:
    max_turns: int = 0  # 0 = unlimited
    max_tool_rounds_per_input: int = 0  # 0 = unlimited
    default_command_timeout_ms: int = 10_000
    max_command_timeout_ms: int = 600_000
    reasoning_effort: str | None = None
    enable_loop_detection: bool = True
    loop_detection_window: int = 10
    max_subagent_depth: int = 1


@dataclass
class UserTurn:
    content: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class AssistantTurn:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    reasoning: str | None = None
    usage: Usage = field(default_factory=Usage)
    response_id: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class ToolResultsTurn:
    results: list[ToolResult] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


@dataclass
class SystemTurn:
    content: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class SteeringTurn:
    content: str = ""
    timestamp: float = field(default_factory=time.time)


Turn = UserTurn | AssistantTurn | ToolResultsTurn | SystemTurn | SteeringTurn


class Session:
    """Central orchestrator for the agentic loop."""

    def __init__(
        self,
        profile: BaseProfile,
        llm_client: Any,
        execution_env: Any = None,
        config: SessionConfig | None = None,
    ) -> None:
        self.id = str(uuid.uuid4())
        self.profile = profile
        self.llm_client = llm_client
        self.execution_env = execution_env
        self.config = config or SessionConfig()
        self.history: list[Turn] = []
        self.event_emitter = EventEmitter()
        self.steering_queue = SteeringQueue()
        self.followup_queue = FollowUpQueue()
        self.state = SessionState.IDLE
        self.abort_signaled = False
        self._tool_signatures: list[str] = []
        self._total_turns = 0

    async def submit(self, user_input: str) -> None:
        """Submit user input and run the agentic loop."""
        await process_input(self, user_input)

    def steer(self, message: str) -> None:
        """Inject a steering message into the next tool round."""
        self.steering_queue.enqueue_sync(message)

    async def follow_up(self, message: str) -> None:
        """Queue a follow-up message to process after current input."""
        await self.followup_queue.enqueue(message)

    def abort(self) -> None:
        """Signal the session to stop."""
        self.abort_signaled = True

    def close(self) -> None:
        """Close the session."""
        self.state = SessionState.CLOSED

    async def _emit(self, kind: EventKind, **data: Any) -> None:
        event = SessionEvent(kind=kind, session_id=self.id, data=data)
        await self.event_emitter.emit(event)


def _convert_history_to_messages(history: list[Turn]) -> list[Message]:
    """Convert session history to LLM messages."""
    messages: list[Message] = []
    for turn in history:
        if isinstance(turn, UserTurn):
            messages.append(Message.user(turn.content))
        elif isinstance(turn, AssistantTurn):
            if turn.tool_calls:
                # Build assistant message with tool calls
                msg = Message.assistant(turn.content)
                msg.tool_calls = turn.tool_calls
                messages.append(msg)
            else:
                messages.append(Message.assistant(turn.content))
        elif isinstance(turn, ToolResultsTurn):
            for tr in turn.results:
                content = tr.content if isinstance(tr.content, str) else str(tr.content)
                messages.append(
                    Message.tool_result(
                        tool_call_id=tr.tool_call_id,
                        content=content,
                        is_error=tr.is_error,
                    )
                )
        elif isinstance(turn, (SteeringTurn, SystemTurn)):
            messages.append(Message.user(turn.content))
    return messages


async def process_input(session: Session, user_input: str) -> None:
    """Run the core agentic loop for a single user input."""
    session.state = SessionState.PROCESSING
    session.history.append(UserTurn(content=user_input))
    await session._emit(EventKind.USER_INPUT, content=user_input)

    # Drain pending steering messages
    await _drain_steering(session)

    round_count = 0

    while True:
        # 1. Check limits
        if (
            session.config.max_tool_rounds_per_input > 0
            and round_count >= session.config.max_tool_rounds_per_input
        ):
            await session._emit(EventKind.TURN_LIMIT, round=round_count)
            break

        session._total_turns += 1
        if session.config.max_turns > 0 and session._total_turns >= session.config.max_turns:
            await session._emit(EventKind.TURN_LIMIT, total_turns=session._total_turns)
            break

        if session.abort_signaled:
            break

        # 2. Build LLM request
        system_prompt = session.profile.build_system_prompt()
        messages = _convert_history_to_messages(session.history)
        tool_defs = session.profile.tools()

        request = Request(
            model=session.profile.model,
            messages=[Message.system(system_prompt)] + messages,
            tools=tool_defs if tool_defs else None,
            reasoning_effort=session.config.reasoning_effort,
            provider=session.profile.id,
            provider_options=session.profile.provider_options(),
        )

        # 3. Call LLM
        response = await session.llm_client.complete(request)

        # 4. Record assistant turn
        assistant_turn = AssistantTurn(
            content=response.text,
            tool_calls=response.tool_calls,
            reasoning=response.reasoning,
            usage=response.usage,
            response_id=response.id,
        )
        session.history.append(assistant_turn)
        await session._emit(
            EventKind.ASSISTANT_TEXT_END,
            text=response.text,
            reasoning=response.reasoning,
        )

        # 5. If no tool calls, natural completion
        if not response.tool_calls:
            break

        # 6. Execute tool calls
        round_count += 1
        results = await _execute_tool_calls(session, response.tool_calls)
        session.history.append(ToolResultsTurn(results=results))

        # 7. Drain steering messages
        await _drain_steering(session)

        # 8. Loop detection
        if session.config.enable_loop_detection:
            for tc in response.tool_calls:
                session._tool_signatures.append(
                    _tool_call_signature(tc.name, tc.arguments)
                )
            if detect_loop(session._tool_signatures, session.config.loop_detection_window):
                warning = (
                    f"Loop detected: the last {session.config.loop_detection_window} "
                    "tool calls follow a repeating pattern. Try a different approach."
                )
                session.history.append(SteeringTurn(content=warning))
                await session._emit(EventKind.LOOP_DETECTION, message=warning)

    # Process follow-up messages
    next_input = await session.followup_queue.dequeue()
    if next_input is not None:
        await process_input(session, next_input)
        return

    session.state = SessionState.IDLE


async def _drain_steering(session: Session) -> None:
    """Drain all pending steering messages into history."""
    messages = await session.steering_queue.drain()
    for msg in messages:
        session.history.append(SteeringTurn(content=msg))
        await session._emit(EventKind.STEERING_INJECTED, content=msg)


async def _execute_tool_calls(
    session: Session, tool_calls: list[ToolCall]
) -> list[ToolResult]:
    """Execute tool calls, concurrently if supported."""
    registry = session.profile.tool_registry

    async def run_one(tc: ToolCall) -> ToolResult:
        await session._emit(
            EventKind.TOOL_CALL_START, tool_name=tc.name, call_id=tc.id
        )
        result = await registry.execute(tc.name, tc.arguments)
        result.tool_call_id = tc.id

        # Emit full untruncated output
        await session._emit(
            EventKind.TOOL_CALL_END,
            tool_name=tc.name,
            call_id=tc.id,
            output=result.content,
            is_error=result.is_error,
        )

        # Truncate for LLM consumption
        if isinstance(result.content, str):
            truncated = truncate_output(result.content, tc.name)
            result.content = truncated.text

        return result

    if session.profile.supports_parallel_tool_calls and len(tool_calls) > 1:
        results = await asyncio.gather(*[run_one(tc) for tc in tool_calls])
        return list(results)
    else:
        return [await run_one(tc) for tc in tool_calls]
