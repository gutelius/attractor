"""Tests for Anthropic Messages API adapter."""

import json
import pytest
import httpx
from pytest_httpx import HTTPXMock

from attractor_llm.providers.anthropic import AnthropicAdapter
from attractor_llm.types import (
    ContentKind,
    ContentPart,
    Message,
    Request,
    Role,
    StreamEventType,
    ThinkingData,
    ToolCallData,
    ToolChoice,
    ToolDefinition,
    Usage,
)
from attractor_llm.errors import AuthenticationError, RateLimitError


@pytest.fixture
def adapter() -> AnthropicAdapter:
    return AnthropicAdapter(api_key="test-key")


def _make_response(
    text: str = "Hello!",
    tool_uses: list | None = None,
    thinking: list | None = None,
    usage: dict | None = None,
    stop_reason: str = "end_turn",
) -> dict:
    content = []
    if thinking:
        content.extend(thinking)
    if text:
        content.append({"type": "text", "text": text})
    if tool_uses:
        content.extend(tool_uses)
    return {
        "id": "msg_123",
        "model": "claude-opus-4-6",
        "type": "message",
        "role": "assistant",
        "content": content,
        "stop_reason": stop_reason,
        "usage": usage or {"input_tokens": 10, "output_tokens": 5},
    }


class TestAnthropicComplete:
    @pytest.mark.asyncio
    async def test_simple_text(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json=_make_response("The answer is 42."),
        )
        resp = await adapter.complete(
            Request(model="claude-opus-4-6", messages=[Message.user("What is 6*7?")])
        )
        assert resp.text == "The answer is 42."
        assert resp.provider == "anthropic"
        assert resp.finish_reason.reason == "stop"

    @pytest.mark.asyncio
    async def test_tool_use(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json=_make_response(
                text="",
                tool_uses=[{
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "get_weather",
                    "input": {"city": "SF"},
                }],
                stop_reason="tool_use",
            ),
        )
        resp = await adapter.complete(
            Request(model="claude-opus-4-6", messages=[Message.user("Weather?")])
        )
        assert resp.finish_reason.reason == "tool_calls"
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "get_weather"

    @pytest.mark.asyncio
    async def test_thinking_blocks(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json=_make_response(
                text="42",
                thinking=[{
                    "type": "thinking",
                    "thinking": "Let me calculate...",
                    "signature": "sig_abc",
                }],
            ),
        )
        resp = await adapter.complete(
            Request(model="claude-opus-4-6", messages=[Message.user("Think")])
        )
        assert resp.reasoning == "Let me calculate..."
        assert resp.text == "42"

    @pytest.mark.asyncio
    async def test_cache_tokens(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json=_make_response(
                usage={
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 80,
                    "cache_creation_input_tokens": 10,
                }
            ),
        )
        resp = await adapter.complete(
            Request(model="claude-opus-4-6", messages=[Message.user("cached")])
        )
        assert resp.usage.cache_read_tokens == 80
        assert resp.usage.cache_write_tokens == 10


class TestAnthropicMessageTranslation:
    @pytest.mark.asyncio
    async def test_system_extraction(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="claude-opus-4-6",
                messages=[
                    Message.system("Be helpful."),
                    Message.user("Hi"),
                ],
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert body["system"] == "Be helpful."
        assert all(m["role"] != "system" for m in body["messages"])

    @pytest.mark.asyncio
    async def test_strict_alternation_merging(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="claude-opus-4-6",
                messages=[
                    Message.user("Hello"),
                    Message.user("How are you?"),  # Consecutive user - should merge
                ],
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"
        assert len(body["messages"][0]["content"]) == 2

    @pytest.mark.asyncio
    async def test_tool_result_in_user_message(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="claude-opus-4-6",
                messages=[
                    Message.user("weather?"),
                    Message(
                        role=Role.ASSISTANT,
                        content=[ContentPart(
                            kind=ContentKind.TOOL_CALL,
                            tool_call=ToolCallData(id="toolu_1", name="weather", arguments={}),
                        )],
                    ),
                    Message.tool_result(tool_call_id="toolu_1", content="72F"),
                ],
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        # Tool result should be in a user message
        tool_msg = body["messages"][-1]
        assert tool_msg["role"] == "user"
        assert tool_msg["content"][0]["type"] == "tool_result"
        assert tool_msg["content"][0]["tool_use_id"] == "toolu_1"

    @pytest.mark.asyncio
    async def test_max_tokens_default(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json=_make_response(),
        )
        await adapter.complete(
            Request(model="claude-opus-4-6", messages=[Message.user("Hi")])
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert body["max_tokens"] == 4096


class TestAnthropicToolChoice:
    @pytest.mark.asyncio
    async def test_auto(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="claude-opus-4-6",
                messages=[Message.user("Hi")],
                tools=[ToolDefinition(name="t", description="d", parameters={"type": "object"})],
                tool_choice=ToolChoice(mode="auto"),
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert body["tool_choice"] == {"type": "auto"}

    @pytest.mark.asyncio
    async def test_none_omits_tools(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="claude-opus-4-6",
                messages=[Message.user("Hi")],
                tools=[ToolDefinition(name="t", description="d", parameters={"type": "object"})],
                tool_choice=ToolChoice(mode="none"),
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert "tools" not in body
        assert "tool_choice" not in body

    @pytest.mark.asyncio
    async def test_required(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="claude-opus-4-6",
                messages=[Message.user("Hi")],
                tools=[ToolDefinition(name="t", description="d", parameters={"type": "object"})],
                tool_choice=ToolChoice(mode="required"),
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert body["tool_choice"] == {"type": "any"}

    @pytest.mark.asyncio
    async def test_named(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="claude-opus-4-6",
                messages=[Message.user("Hi")],
                tools=[ToolDefinition(name="get_weather", description="d", parameters={"type": "object"})],
                tool_choice=ToolChoice(mode="named", tool_name="get_weather"),
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert body["tool_choice"] == {"type": "tool", "name": "get_weather"}


class TestAnthropicBetaHeaders:
    @pytest.mark.asyncio
    async def test_beta_headers(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="claude-opus-4-6",
                messages=[Message.user("Hi")],
                provider_options={
                    "anthropic": {
                        "beta_headers": ["interleaved-thinking-2025-05-14", "prompt-caching-2024-07-31"]
                    }
                },
            )
        )
        sent = httpx_mock.get_requests()[0]
        assert "interleaved-thinking-2025-05-14,prompt-caching-2024-07-31" in sent.headers.get("anthropic-beta", "")


class TestAnthropicErrors:
    @pytest.mark.asyncio
    async def test_auth_error(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            status_code=401,
            json={"error": {"message": "Invalid API key", "type": "authentication_error"}},
        )
        with pytest.raises(AuthenticationError):
            await adapter.complete(
                Request(model="claude-opus-4-6", messages=[Message.user("Hi")])
            )

    @pytest.mark.asyncio
    async def test_rate_limit(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            status_code=429,
            json={"error": {"message": "Rate limited", "type": "rate_limit_error"}},
        )
        with pytest.raises(RateLimitError):
            await adapter.complete(
                Request(model="claude-opus-4-6", messages=[Message.user("Hi")])
            )


class TestAnthropicStreaming:
    @pytest.mark.asyncio
    async def test_text_stream(self, httpx_mock: HTTPXMock, adapter: AnthropicAdapter):
        sse_lines = "\n".join([
            'event: message_start',
            'data: {"type":"message_start","message":{"id":"msg_1","model":"claude-opus-4-6","usage":{"input_tokens":10}}}',
            '',
            'event: content_block_start',
            'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}',
            '',
            'event: content_block_delta',
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}',
            '',
            'event: content_block_delta',
            'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" world"}}',
            '',
            'event: content_block_stop',
            'data: {"type":"content_block_stop","index":0}',
            '',
            'event: message_delta',
            'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":5}}',
            '',
            'event: message_stop',
            'data: {"type":"message_stop"}',
            '',
        ])
        httpx_mock.add_response(
            url="https://api.anthropic.com/v1/messages",
            stream=httpx.ByteStream(sse_lines.encode()),
        )
        events = []
        async for event in adapter.stream(
            Request(model="claude-opus-4-6", messages=[Message.user("Hi")])
        ):
            events.append(event)

        types = [e.type for e in events]
        assert StreamEventType.STREAM_START in types
        assert StreamEventType.TEXT_START in types
        assert StreamEventType.TEXT_DELTA in types
        assert StreamEventType.TEXT_END in types
        assert StreamEventType.FINISH in types
        deltas = [e.delta for e in events if e.type == StreamEventType.TEXT_DELTA]
        assert "Hello" in deltas
        assert " world" in deltas
