"""Tests for OpenAI Responses API adapter."""

import json
import pytest
import httpx
from pytest_httpx import HTTPXMock

from attractor_llm.providers.openai import OpenAIAdapter
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
    Usage,
)
from attractor_llm.errors import AuthenticationError, RateLimitError


@pytest.fixture
def adapter(httpx_mock: HTTPXMock) -> OpenAIAdapter:
    return OpenAIAdapter(api_key="test-key", base_url="https://api.openai.com")


def _make_response(
    text: str = "Hello!",
    tool_calls: list | None = None,
    usage: dict | None = None,
    model: str = "gpt-5.2",
) -> dict:
    output = []
    if text:
        output.append({
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        })
    if tool_calls:
        for tc in tool_calls:
            output.append({
                "type": "function_call",
                "call_id": tc["id"],
                "name": tc["name"],
                "arguments": json.dumps(tc["arguments"]),
            })
    return {
        "id": "resp_123",
        "model": model,
        "status": "completed",
        "output": output,
        "usage": usage or {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
    }


class TestOpenAIComplete:
    @pytest.mark.asyncio
    async def test_simple_text(self, httpx_mock: HTTPXMock, adapter: OpenAIAdapter):
        httpx_mock.add_response(
            url="https://api.openai.com/v1/responses",
            json=_make_response("The answer is 42."),
        )
        resp = await adapter.complete(
            Request(model="gpt-5.2", messages=[Message.user("What is 6*7?")])
        )
        assert resp.text == "The answer is 42."
        assert resp.provider == "openai"
        assert resp.finish_reason.reason == "stop"
        assert resp.usage.input_tokens == 10

    @pytest.mark.asyncio
    async def test_tool_calls(self, httpx_mock: HTTPXMock, adapter: OpenAIAdapter):
        httpx_mock.add_response(
            url="https://api.openai.com/v1/responses",
            json=_make_response(
                text="",
                tool_calls=[{"id": "call_1", "name": "get_weather", "arguments": {"city": "SF"}}],
            ),
        )
        resp = await adapter.complete(
            Request(model="gpt-5.2", messages=[Message.user("Weather?")])
        )
        assert resp.finish_reason.reason == "tool_calls"
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "get_weather"
        assert resp.tool_calls[0].arguments == {"city": "SF"}

    @pytest.mark.asyncio
    async def test_reasoning_tokens(self, httpx_mock: HTTPXMock, adapter: OpenAIAdapter):
        httpx_mock.add_response(
            url="https://api.openai.com/v1/responses",
            json=_make_response(
                usage={
                    "input_tokens": 50,
                    "output_tokens": 100,
                    "total_tokens": 150,
                    "output_tokens_details": {"reasoning_tokens": 80},
                }
            ),
        )
        resp = await adapter.complete(
            Request(model="gpt-5.2", messages=[Message.user("Think hard")])
        )
        assert resp.usage.reasoning_tokens == 80

    @pytest.mark.asyncio
    async def test_cache_read_tokens(self, httpx_mock: HTTPXMock, adapter: OpenAIAdapter):
        httpx_mock.add_response(
            url="https://api.openai.com/v1/responses",
            json=_make_response(
                usage={
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "total_tokens": 110,
                    "input_tokens_details": {"cached_tokens": 60},
                }
            ),
        )
        resp = await adapter.complete(
            Request(model="gpt-5.2", messages=[Message.user("cached?")])
        )
        assert resp.usage.cache_read_tokens == 60


class TestOpenAIMessageTranslation:
    @pytest.mark.asyncio
    async def test_system_to_instructions(self, httpx_mock: HTTPXMock, adapter: OpenAIAdapter):
        httpx_mock.add_response(
            url="https://api.openai.com/v1/responses",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="gpt-5.2",
                messages=[
                    Message.system("You are helpful."),
                    Message.user("Hi"),
                ],
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert body["instructions"] == "You are helpful."
        # System should not be in input
        assert all(
            item.get("role") != "system"
            for item in body["input"]
            if isinstance(item, dict) and "role" in item
        )

    @pytest.mark.asyncio
    async def test_tool_result_translation(self, httpx_mock: HTTPXMock, adapter: OpenAIAdapter):
        httpx_mock.add_response(
            url="https://api.openai.com/v1/responses",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="gpt-5.2",
                messages=[
                    Message.user("weather?"),
                    Message.tool_result(tool_call_id="call_1", content="72F"),
                ],
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        fn_outputs = [i for i in body["input"] if i.get("type") == "function_call_output"]
        assert len(fn_outputs) == 1
        assert fn_outputs[0]["call_id"] == "call_1"
        assert fn_outputs[0]["output"] == "72F"


class TestOpenAIToolChoice:
    @pytest.mark.asyncio
    async def test_modes(self, httpx_mock: HTTPXMock, adapter: OpenAIAdapter):
        for mode, expected in [
            ("auto", "auto"),
            ("none", "none"),
            ("required", "required"),
        ]:
            httpx_mock.add_response(
                url="https://api.openai.com/v1/responses",
                json=_make_response(),
            )
            await adapter.complete(
                Request(
                    model="gpt-5.2",
                    messages=[Message.user("Hi")],
                    tool_choice=ToolChoice(mode=mode),
                )
            )
            sent = httpx_mock.get_requests()[-1]
            body = json.loads(sent.content)
            assert body["tool_choice"] == expected

    @pytest.mark.asyncio
    async def test_named(self, httpx_mock: HTTPXMock, adapter: OpenAIAdapter):
        httpx_mock.add_response(
            url="https://api.openai.com/v1/responses",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="gpt-5.2",
                messages=[Message.user("Hi")],
                tool_choice=ToolChoice(mode="named", tool_name="get_weather"),
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert body["tool_choice"] == {"type": "function", "name": "get_weather"}


class TestOpenAIReasoningEffort:
    @pytest.mark.asyncio
    async def test_passthrough(self, httpx_mock: HTTPXMock, adapter: OpenAIAdapter):
        httpx_mock.add_response(
            url="https://api.openai.com/v1/responses",
            json=_make_response(),
        )
        await adapter.complete(
            Request(
                model="gpt-5.2",
                messages=[Message.user("Think")],
                reasoning_effort="high",
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert body["reasoning"] == {"effort": "high"}


class TestOpenAIToolDefinition:
    @pytest.mark.asyncio
    async def test_translation(self, httpx_mock: HTTPXMock, adapter: OpenAIAdapter):
        httpx_mock.add_response(
            url="https://api.openai.com/v1/responses",
            json=_make_response(),
        )
        tool = ToolDefinition(
            name="get_weather",
            description="Get weather",
            parameters={"type": "object", "properties": {"city": {"type": "string"}}},
        )
        await adapter.complete(
            Request(model="gpt-5.2", messages=[Message.user("Hi")], tools=[tool])
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert len(body["tools"]) == 1
        assert body["tools"][0]["type"] == "function"
        assert body["tools"][0]["name"] == "get_weather"


class TestOpenAIErrors:
    @pytest.mark.asyncio
    async def test_auth_error(self, httpx_mock: HTTPXMock, adapter: OpenAIAdapter):
        httpx_mock.add_response(
            url="https://api.openai.com/v1/responses",
            status_code=401,
            json={"error": {"message": "Invalid API key", "type": "auth_error"}},
        )
        with pytest.raises(AuthenticationError):
            await adapter.complete(
                Request(model="gpt-5.2", messages=[Message.user("Hi")])
            )

    @pytest.mark.asyncio
    async def test_rate_limit(self, httpx_mock: HTTPXMock, adapter: OpenAIAdapter):
        httpx_mock.add_response(
            url="https://api.openai.com/v1/responses",
            status_code=429,
            json={"error": {"message": "Rate limited"}},
            headers={"retry-after": "5"},
        )
        with pytest.raises(RateLimitError) as exc_info:
            await adapter.complete(
                Request(model="gpt-5.2", messages=[Message.user("Hi")])
            )
        assert exc_info.value.retry_after == 5.0


class TestOpenAIStreaming:
    @pytest.mark.asyncio
    async def test_text_stream(self, httpx_mock: HTTPXMock, adapter: OpenAIAdapter):
        sse_lines = [
            'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":"Hello"}\n',
            'event: response.output_text.delta\ndata: {"type":"response.output_text.delta","delta":" world"}\n',
            'event: response.completed\ndata: {"type":"response.completed","response":{"id":"resp_1","model":"gpt-5.2","status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":"Hello world"}]}],"usage":{"input_tokens":5,"output_tokens":2,"total_tokens":7}}}\n',
            "data: [DONE]\n",
        ]
        httpx_mock.add_response(
            url="https://api.openai.com/v1/responses",
            stream=httpx.ByteStream(
                "\n".join(sse_lines).encode()
            ),
        )
        events = []
        async for event in adapter.stream(
            Request(model="gpt-5.2", messages=[Message.user("Hi")])
        ):
            events.append(event)

        types = [e.type for e in events]
        assert StreamEventType.TEXT_START in types
        assert StreamEventType.TEXT_DELTA in types
        assert StreamEventType.FINISH in types
        deltas = [e.delta for e in events if e.type == StreamEventType.TEXT_DELTA]
        assert "Hello" in deltas
