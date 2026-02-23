"""Tests for session and core agentic loop."""

import asyncio

import pytest

from attractor_agent.events import EventKind, SessionEvent
from attractor_agent.session import (
    AssistantTurn,
    Session,
    SessionConfig,
    SessionState,
    SteeringTurn,
    ToolResultsTurn,
    UserTurn,
    process_input,
)
from attractor_agent.profiles.base import BaseProfile
from attractor_agent.tools.registry import ToolRegistry
from attractor_llm.types import (
    ContentKind,
    ContentPart,
    FinishReason,
    Message,
    Response,
    Role,
    ToolCall,
    ToolCallData,
    ToolDefinition,
    ToolResult,
    Usage,
)


class MockLLMClient:
    """Mock LLM client that returns scripted responses."""

    def __init__(self, responses: list[Response]):
        self._responses = list(responses)
        self._call_count = 0

    async def complete(self, request):
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[idx]


def _text_response(text: str) -> Response:
    msg = Message(
        role=Role.ASSISTANT,
        content=[ContentPart(kind=ContentKind.TEXT, text=text)],
    )
    return Response(
        id="resp-1",
        model="test",
        message=msg,
        usage=Usage(input_tokens=10, output_tokens=5),
        finish_reason=FinishReason(reason="stop"),
    )


def _tool_response(tool_calls: list[ToolCall], text: str = "") -> Response:
    parts: list[ContentPart] = []
    if text:
        parts.append(ContentPart(kind=ContentKind.TEXT, text=text))
    for tc in tool_calls:
        parts.append(ContentPart(
            kind=ContentKind.TOOL_CALL,
            tool_call=ToolCallData(id=tc.id, name=tc.name, arguments=tc.arguments),
        ))
    msg = Message(role=Role.ASSISTANT, content=parts)
    return Response(
        id="resp-2",
        model="test",
        message=msg,
        usage=Usage(input_tokens=10, output_tokens=5),
        finish_reason=FinishReason(reason="tool_calls"),
    )


def _make_profile_with_tool() -> BaseProfile:
    """Create a profile with a simple echo tool."""
    profile = BaseProfile(id="test", model="test-model")

    async def echo_tool(message: str) -> str:
        return f"echoed: {message}"

    tool_def = ToolDefinition(
        name="echo",
        description="Echo a message",
        parameters={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
        execute=echo_tool,
    )
    profile.tool_registry.register(tool_def, echo_tool)
    return profile


class TestSessionCreation:
    def test_initial_state(self):
        profile = BaseProfile(id="test", model="test")
        client = MockLLMClient([])
        session = Session(profile=profile, llm_client=client)
        assert session.state == SessionState.IDLE
        assert session.history == []
        assert not session.abort_signaled

    def test_has_uuid(self):
        session = Session(profile=BaseProfile(), llm_client=MockLLMClient([]))
        assert len(session.id) > 0


class TestProcessInput:
    async def test_simple_text_response(self):
        profile = BaseProfile(id="test", model="test")
        client = MockLLMClient([_text_response("Hello!")])
        session = Session(profile=profile, llm_client=client)

        await session.submit("Hi")

        assert session.state == SessionState.IDLE
        assert len(session.history) == 2  # UserTurn + AssistantTurn
        assert isinstance(session.history[0], UserTurn)
        assert isinstance(session.history[1], AssistantTurn)
        assert session.history[1].content == "Hello!"

    async def test_tool_execution_loop(self):
        profile = _make_profile_with_tool()
        tool_call = ToolCall(id="tc1", name="echo", arguments={"message": "hi"})
        client = MockLLMClient([
            _tool_response([tool_call]),
            _text_response("Done!"),
        ])
        session = Session(profile=profile, llm_client=client)

        await session.submit("Use echo")

        # History: User, Assistant(tool_call), ToolResults, Assistant(text)
        assert len(session.history) == 4
        assert isinstance(session.history[2], ToolResultsTurn)
        assert "echoed: hi" in str(session.history[2].results[0].content)
        assert session.history[3].content == "Done!"

    async def test_max_tool_rounds(self):
        profile = _make_profile_with_tool()
        tool_call = ToolCall(id="tc1", name="echo", arguments={"message": "loop"})
        # Always returns tool calls
        client = MockLLMClient([_tool_response([tool_call])] * 10)
        config = SessionConfig(max_tool_rounds_per_input=2)
        session = Session(profile=profile, llm_client=client, config=config)

        await session.submit("Go")

        # Should stop after 2 rounds
        assert client._call_count == 2

    async def test_max_turns(self):
        profile = BaseProfile(id="test", model="test")
        client = MockLLMClient([_text_response("ok")] * 5)
        config = SessionConfig(max_turns=2)
        session = Session(profile=profile, llm_client=client, config=config)

        await session.submit("first")
        await session.submit("second")

        # Second call should hit turn limit quickly
        assert session.state == SessionState.IDLE

    async def test_abort_signal(self):
        profile = _make_profile_with_tool()
        tool_call = ToolCall(id="tc1", name="echo", arguments={"message": "x"})
        client = MockLLMClient([_tool_response([tool_call])] * 10)
        session = Session(profile=profile, llm_client=client)

        # Abort after first tool result via event callback
        call_count = 0

        async def abort_after_first(event):
            nonlocal call_count
            if event.kind == EventKind.TOOL_CALL_END:
                call_count += 1
                if call_count >= 1:
                    session.abort()

        session.event_emitter.on_event(abort_after_first)
        await session.submit("Go forever")
        assert session.abort_signaled

    async def test_steering_injection(self):
        profile = _make_profile_with_tool()
        tool_call = ToolCall(id="tc1", name="echo", arguments={"message": "x"})
        client = MockLLMClient([
            _tool_response([tool_call]),
            _text_response("Final"),
        ])
        session = Session(profile=profile, llm_client=client)
        session.steer("Focus on tests")

        await session.submit("Start")

        # Steering should appear in history
        steering_turns = [t for t in session.history if isinstance(t, SteeringTurn)]
        assert len(steering_turns) >= 1
        assert "Focus on tests" in steering_turns[0].content

    async def test_follow_up_queue(self):
        profile = BaseProfile(id="test", model="test")
        client = MockLLMClient([
            _text_response("First response"),
            _text_response("Follow-up response"),
        ])
        session = Session(profile=profile, llm_client=client)
        await session.followup_queue.enqueue("follow-up message")

        await session.submit("initial")

        # Both inputs should have been processed
        user_turns = [t for t in session.history if isinstance(t, UserTurn)]
        assert len(user_turns) == 2
        assert user_turns[1].content == "follow-up message"


class TestEvents:
    async def test_emits_user_input_event(self):
        profile = BaseProfile(id="test", model="test")
        client = MockLLMClient([_text_response("ok")])
        session = Session(profile=profile, llm_client=client)

        events: list[SessionEvent] = []
        session.event_emitter.on_event(lambda e: events.append(e))

        await session.submit("Hello")

        kinds = [e.kind for e in events]
        assert EventKind.USER_INPUT in kinds
        assert EventKind.ASSISTANT_TEXT_END in kinds

    async def test_emits_tool_events(self):
        profile = _make_profile_with_tool()
        tool_call = ToolCall(id="tc1", name="echo", arguments={"message": "hi"})
        client = MockLLMClient([
            _tool_response([tool_call]),
            _text_response("Done"),
        ])
        session = Session(profile=profile, llm_client=client)

        events: list[SessionEvent] = []
        session.event_emitter.on_event(lambda e: events.append(e))

        await session.submit("Go")

        kinds = [e.kind for e in events]
        assert EventKind.TOOL_CALL_START in kinds
        assert EventKind.TOOL_CALL_END in kinds

    async def test_tool_call_end_has_full_output(self):
        profile = _make_profile_with_tool()
        tool_call = ToolCall(id="tc1", name="echo", arguments={"message": "hi"})
        client = MockLLMClient([
            _tool_response([tool_call]),
            _text_response("Done"),
        ])
        session = Session(profile=profile, llm_client=client)

        events: list[SessionEvent] = []
        session.event_emitter.on_event(lambda e: events.append(e))

        await session.submit("Go")

        end_events = [e for e in events if e.kind == EventKind.TOOL_CALL_END]
        assert len(end_events) == 1
        assert "echoed: hi" in str(end_events[0].data.get("output"))


class TestLoopDetection:
    async def test_detects_repeating_pattern(self):
        profile = _make_profile_with_tool()
        # Same tool call every time
        tool_call = ToolCall(id="tc1", name="echo", arguments={"message": "same"})
        client = MockLLMClient([_tool_response([tool_call])] * 15 + [_text_response("done")])
        config = SessionConfig(
            enable_loop_detection=True,
            loop_detection_window=10,
            max_tool_rounds_per_input=15,
        )
        session = Session(profile=profile, llm_client=client, config=config)

        events: list[SessionEvent] = []
        session.event_emitter.on_event(lambda e: events.append(e))

        await session.submit("Go")

        loop_events = [e for e in events if e.kind == EventKind.LOOP_DETECTION]
        assert len(loop_events) >= 1

    async def test_no_false_positive(self):
        profile = _make_profile_with_tool()
        # Different tool calls each time
        responses = [
            _tool_response([ToolCall(id=f"tc{i}", name="echo", arguments={"message": f"msg{i}"})])
            for i in range(5)
        ]
        responses.append(_text_response("done"))
        client = MockLLMClient(responses)
        config = SessionConfig(enable_loop_detection=True, max_tool_rounds_per_input=5)
        session = Session(profile=profile, llm_client=client, config=config)

        events: list[SessionEvent] = []
        session.event_emitter.on_event(lambda e: events.append(e))

        await session.submit("Go")

        loop_events = [e for e in events if e.kind == EventKind.LOOP_DETECTION]
        assert len(loop_events) == 0


class TestSessionState:
    async def test_idle_after_completion(self):
        profile = BaseProfile(id="test", model="test")
        client = MockLLMClient([_text_response("ok")])
        session = Session(profile=profile, llm_client=client)
        await session.submit("Hi")
        assert session.state == SessionState.IDLE

    def test_close(self):
        session = Session(profile=BaseProfile(), llm_client=MockLLMClient([]))
        session.close()
        assert session.state == SessionState.CLOSED
