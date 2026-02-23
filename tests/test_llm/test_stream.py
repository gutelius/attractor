"""Tests for attractor_llm.stream."""

import pytest

from attractor_llm.stream import StreamAccumulator, StreamResult
from attractor_llm.types import (
    FinishReason,
    StreamEvent,
    StreamEventType,
    ToolCall,
    Usage,
)


class TestStreamAccumulator:
    def test_text_accumulation(self):
        acc = StreamAccumulator()
        acc.process(StreamEvent(type=StreamEventType.TEXT_START))
        acc.process(StreamEvent(type=StreamEventType.TEXT_DELTA, delta="Hello"))
        acc.process(StreamEvent(type=StreamEventType.TEXT_DELTA, delta=" world"))
        acc.process(StreamEvent(type=StreamEventType.TEXT_END))
        acc.process(StreamEvent(
            type=StreamEventType.FINISH,
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=5, output_tokens=2, total_tokens=7),
        ))

        assert acc.text == "Hello world"
        resp = acc.response()
        assert resp.text == "Hello world"
        assert resp.finish_reason.reason == "stop"
        assert resp.usage.total_tokens == 7

    def test_reasoning_accumulation(self):
        acc = StreamAccumulator()
        acc.process(StreamEvent(type=StreamEventType.REASONING_START))
        acc.process(StreamEvent(type=StreamEventType.REASONING_DELTA, reasoning_delta="Think..."))
        acc.process(StreamEvent(type=StreamEventType.REASONING_END))
        acc.process(StreamEvent(type=StreamEventType.TEXT_DELTA, delta="Answer"))
        acc.process(StreamEvent(type=StreamEventType.FINISH))

        assert acc.reasoning == "Think..."
        assert acc.text == "Answer"

    def test_tool_call_accumulation(self):
        tc = ToolCall(id="call_1", name="fn", arguments={"a": 1})
        acc = StreamAccumulator()
        acc.process(StreamEvent(type=StreamEventType.TOOL_CALL_START, tool_call=tc))
        acc.process(StreamEvent(type=StreamEventType.TOOL_CALL_END, tool_call=tc))
        acc.process(StreamEvent(type=StreamEventType.FINISH))

        resp = acc.response()
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "fn"

    def test_no_reasoning_returns_none(self):
        acc = StreamAccumulator()
        acc.process(StreamEvent(type=StreamEventType.TEXT_DELTA, delta="text"))
        acc.process(StreamEvent(type=StreamEventType.FINISH))
        assert acc.reasoning is None


class TestStreamResult:
    @pytest.mark.asyncio
    async def test_iteration(self):
        async def gen():
            yield StreamEvent(type=StreamEventType.TEXT_DELTA, delta="Hi")
            yield StreamEvent(type=StreamEventType.FINISH,
                              finish_reason=FinishReason(reason="stop"),
                              usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2))

        result = StreamResult(gen())
        events = []
        async for event in result:
            events.append(event)

        assert len(events) == 2
        resp = result.response()
        assert resp.text == "Hi"

    @pytest.mark.asyncio
    async def test_text_stream(self):
        async def gen():
            yield StreamEvent(type=StreamEventType.TEXT_DELTA, delta="Hello")
            yield StreamEvent(type=StreamEventType.TEXT_DELTA, delta=" world")
            yield StreamEvent(type=StreamEventType.FINISH)

        result = StreamResult(gen())
        texts = []
        async for text in result.text_stream:
            texts.append(text)

        assert texts == ["Hello", " world"]
