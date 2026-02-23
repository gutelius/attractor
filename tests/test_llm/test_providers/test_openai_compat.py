"""Tests for OpenAI-compatible Chat Completions adapter."""

import json
import pytest
import httpx
from pytest_httpx import HTTPXMock

from attractor_llm.providers.openai_compat import OpenAICompatibleAdapter
from attractor_llm.types import (
    ContentKind,
    ContentPart,
    Message,
    Request,
    Role,
    StreamEventType,
    ToolCallData,
    ToolChoice,
    ToolDefinition,
)
from attractor_llm.errors import ServerError


@pytest.fixture
def adapter() -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(
        api_key="test-key", base_url="https://api.example.com"
    )


def _make_response(
    text: str = "Hello!",
    tool_calls: list | None = None,
    finish_reason: str = "stop",
) -> dict:
    message: dict = {"role": "assistant"}
    if text:
        message["content"] = text
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "id": "chatcmpl-123",
        "model": "llama-3",
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


class TestOpenAICompatComplete:
    @pytest.mark.asyncio
    async def test_simple_text(self, httpx_mock: HTTPXMock, adapter: OpenAICompatibleAdapter):
        httpx_mock.add_response(
            url="https://api.example.com/v1/chat/completions",
            json=_make_response("The answer is 42."),
        )
        resp = await adapter.complete(
            Request(model="llama-3", messages=[Message.user("What is 6*7?")])
        )
        assert resp.text == "The answer is 42."
        assert resp.provider == "openai-compatible"
        assert resp.finish_reason.reason == "stop"

    @pytest.mark.asyncio
    async def test_tool_calls(self, httpx_mock: HTTPXMock, adapter: OpenAICompatibleAdapter):
        httpx_mock.add_response(
            url="https://api.example.com/v1/chat/completions",
            json=_make_response(
                text="",
                tool_calls=[{
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": '{"city":"SF"}'},
                }],
                finish_reason="tool_calls",
            ),
        )
        resp = await adapter.complete(
            Request(model="llama-3", messages=[Message.user("Weather?")])
        )
        assert resp.finish_reason.reason == "tool_calls"
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "get_weather"


class TestOpenAICompatMessageTranslation:
    @pytest.mark.asyncio
    async def test_chat_completions_format(self, httpx_mock: HTTPXMock, adapter: OpenAICompatibleAdapter):
        httpx_mock.add_response(
            url="https://api.example.com/v1/chat/completions",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="llama-3",
                messages=[
                    Message.system("Be helpful."),
                    Message.user("Hi"),
                ],
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert body["messages"][0] == {"role": "system", "content": "Be helpful."}
        assert body["messages"][1] == {"role": "user", "content": "Hi"}

    @pytest.mark.asyncio
    async def test_tool_result_format(self, httpx_mock: HTTPXMock, adapter: OpenAICompatibleAdapter):
        httpx_mock.add_response(
            url="https://api.example.com/v1/chat/completions",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="llama-3",
                messages=[
                    Message.user("hi"),
                    Message.tool_result(tool_call_id="call_1", content="72F"),
                ],
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        tool_msg = body["messages"][1]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "call_1"
        assert tool_msg["content"] == "72F"


class TestOpenAICompatStreaming:
    @pytest.mark.asyncio
    async def test_text_stream(self, httpx_mock: HTTPXMock, adapter: OpenAICompatibleAdapter):
        chunks = [
            'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}\n',
            'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}\n',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n',
            "data: [DONE]\n",
        ]
        httpx_mock.add_response(
            url="https://api.example.com/v1/chat/completions",
            stream=httpx.ByteStream("\n".join(chunks).encode()),
        )
        events = []
        async for event in adapter.stream(
            Request(model="llama-3", messages=[Message.user("Hi")])
        ):
            events.append(event)

        types = [e.type for e in events]
        assert StreamEventType.TEXT_START in types
        assert StreamEventType.TEXT_DELTA in types
        assert StreamEventType.FINISH in types


class TestOpenAICompatErrors:
    @pytest.mark.asyncio
    async def test_server_error(self, httpx_mock: HTTPXMock, adapter: OpenAICompatibleAdapter):
        httpx_mock.add_response(
            url="https://api.example.com/v1/chat/completions",
            status_code=500,
            json={"error": {"message": "Internal server error"}},
        )
        with pytest.raises(ServerError):
            await adapter.complete(
                Request(model="llama-3", messages=[Message.user("Hi")])
            )
