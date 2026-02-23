"""Tests for Gemini generateContent API adapter."""

import json
import pytest
import httpx
from pytest_httpx import HTTPXMock

from attractor_llm.providers.gemini import GeminiAdapter
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
from attractor_llm.errors import AuthenticationError, NotFoundError


@pytest.fixture
def adapter() -> GeminiAdapter:
    return GeminiAdapter(api_key="test-key")


def _make_response(
    text: str = "Hello!",
    function_calls: list | None = None,
    usage: dict | None = None,
    finish_reason: str = "STOP",
) -> dict:
    parts = []
    if text:
        parts.append({"text": text})
    if function_calls:
        for fc in function_calls:
            parts.append({"functionCall": fc})
    return {
        "candidates": [{
            "content": {"role": "model", "parts": parts},
            "finishReason": finish_reason,
        }],
        "usageMetadata": usage or {
            "promptTokenCount": 10,
            "candidatesTokenCount": 5,
            "totalTokenCount": 15,
        },
    }


class TestGeminiComplete:
    @pytest.mark.asyncio
    async def test_simple_text(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        httpx_mock.add_response(json=_make_response("The answer is 42."))
        resp = await adapter.complete(
            Request(model="gemini-3-flash-preview", messages=[Message.user("What is 6*7?")])
        )
        assert resp.text == "The answer is 42."
        assert resp.provider == "gemini"
        assert resp.finish_reason.reason == "stop"
        assert resp.usage.input_tokens == 10

    @pytest.mark.asyncio
    async def test_function_call(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        httpx_mock.add_response(
            json=_make_response(
                text="",
                function_calls=[{"name": "get_weather", "args": {"city": "SF"}}],
            ),
        )
        resp = await adapter.complete(
            Request(model="gemini-3-flash-preview", messages=[Message.user("Weather?")])
        )
        assert resp.finish_reason.reason == "tool_calls"
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "get_weather"
        assert resp.tool_calls[0].arguments == {"city": "SF"}
        # Synthetic ID should be generated
        assert resp.tool_calls[0].id.startswith("call_")

    @pytest.mark.asyncio
    async def test_reasoning_tokens(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        httpx_mock.add_response(
            json=_make_response(
                usage={
                    "promptTokenCount": 50,
                    "candidatesTokenCount": 100,
                    "totalTokenCount": 150,
                    "thoughtsTokenCount": 80,
                }
            ),
        )
        resp = await adapter.complete(
            Request(model="gemini-3-flash-preview", messages=[Message.user("Think")])
        )
        assert resp.usage.reasoning_tokens == 80


class TestGeminiMessageTranslation:
    @pytest.mark.asyncio
    async def test_system_to_system_instruction(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        httpx_mock.add_response(json=_make_response())
        await adapter.complete(
            Request(
                model="gemini-3-flash-preview",
                messages=[Message.system("Be helpful."), Message.user("Hi")],
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert body["systemInstruction"]["parts"][0]["text"] == "Be helpful."
        assert all(c["role"] != "system" for c in body["contents"])

    @pytest.mark.asyncio
    async def test_assistant_to_model_role(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        httpx_mock.add_response(json=_make_response())
        await adapter.complete(
            Request(
                model="gemini-3-flash-preview",
                messages=[
                    Message.user("Hi"),
                    Message.assistant("Hello!"),
                    Message.user("How are you?"),
                ],
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        assert body["contents"][1]["role"] == "model"

    @pytest.mark.asyncio
    async def test_tool_result_uses_function_name(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        httpx_mock.add_response(json=_make_response())
        # Pre-register a call_id -> name mapping
        adapter._call_id_to_name["call_abc"] = "get_weather"
        await adapter.complete(
            Request(
                model="gemini-3-flash-preview",
                messages=[
                    Message.user("weather?"),
                    Message.tool_result(tool_call_id="call_abc", content="72F"),
                ],
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        fn_resp = body["contents"][-1]["parts"][0]["functionResponse"]
        assert fn_resp["name"] == "get_weather"
        assert fn_resp["response"] == {"result": "72F"}

    @pytest.mark.asyncio
    async def test_string_result_wrapped(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        """String tool results are wrapped in {"result": "..."}."""
        httpx_mock.add_response(json=_make_response())
        adapter._call_id_to_name["call_x"] = "fn"
        await adapter.complete(
            Request(
                model="gemini-3-flash-preview",
                messages=[Message.tool_result(tool_call_id="call_x", content="hello")],
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        fn_resp = body["contents"][0]["parts"][0]["functionResponse"]
        assert fn_resp["response"] == {"result": "hello"}


class TestGeminiToolChoice:
    @pytest.mark.asyncio
    async def test_modes(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        for mode, expected_mode in [("auto", "AUTO"), ("none", "NONE"), ("required", "ANY")]:
            httpx_mock.add_response(json=_make_response())
            await adapter.complete(
                Request(
                    model="gemini-3-flash-preview",
                    messages=[Message.user("Hi")],
                    tool_choice=ToolChoice(mode=mode),
                )
            )
            sent = httpx_mock.get_requests()[-1]
            body = json.loads(sent.content)
            assert body["toolConfig"]["functionCallingConfig"]["mode"] == expected_mode

    @pytest.mark.asyncio
    async def test_named(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        httpx_mock.add_response(json=_make_response())
        await adapter.complete(
            Request(
                model="gemini-3-flash-preview",
                messages=[Message.user("Hi")],
                tool_choice=ToolChoice(mode="named", tool_name="get_weather"),
            )
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        tc = body["toolConfig"]["functionCallingConfig"]
        assert tc["mode"] == "ANY"
        assert tc["allowedFunctionNames"] == ["get_weather"]


class TestGeminiToolDefinition:
    @pytest.mark.asyncio
    async def test_translation(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        httpx_mock.add_response(json=_make_response())
        tool = ToolDefinition(
            name="get_weather",
            description="Get weather",
            parameters={"type": "object", "properties": {"city": {"type": "string"}}},
        )
        await adapter.complete(
            Request(model="gemini-3-flash-preview", messages=[Message.user("Hi")], tools=[tool])
        )
        sent = httpx_mock.get_requests()[0]
        body = json.loads(sent.content)
        decls = body["tools"][0]["functionDeclarations"]
        assert len(decls) == 1
        assert decls[0]["name"] == "get_weather"


class TestGeminiErrors:
    @pytest.mark.asyncio
    async def test_auth_error(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        httpx_mock.add_response(
            status_code=401,
            json={"error": {"message": "API key invalid", "status": "UNAUTHENTICATED"}},
        )
        with pytest.raises(AuthenticationError):
            await adapter.complete(
                Request(model="gemini-3-flash-preview", messages=[Message.user("Hi")])
            )

    @pytest.mark.asyncio
    async def test_not_found(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        httpx_mock.add_response(
            status_code=404,
            json={"error": {"message": "Model not found", "status": "NOT_FOUND"}},
        )
        with pytest.raises(NotFoundError):
            await adapter.complete(
                Request(model="nonexistent", messages=[Message.user("Hi")])
            )


class TestGeminiStreaming:
    @pytest.mark.asyncio
    async def test_text_stream(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        chunks = [
            'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}]}}],"usageMetadata":{"promptTokenCount":5}}\n',
            'data: {"candidates":[{"content":{"parts":[{"text":" world"}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":5,"candidatesTokenCount":2,"totalTokenCount":7}}\n',
        ]
        httpx_mock.add_response(
            stream=httpx.ByteStream("\n".join(chunks).encode()),
        )
        events = []
        async for event in adapter.stream(
            Request(model="gemini-3-flash-preview", messages=[Message.user("Hi")])
        ):
            events.append(event)

        types = [e.type for e in events]
        assert StreamEventType.TEXT_START in types
        assert StreamEventType.TEXT_DELTA in types
        assert StreamEventType.FINISH in types

    @pytest.mark.asyncio
    async def test_function_call_stream(self, httpx_mock: HTTPXMock, adapter: GeminiAdapter):
        chunk = 'data: {"candidates":[{"content":{"parts":[{"functionCall":{"name":"get_weather","args":{"city":"SF"}}}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":5,"candidatesTokenCount":10,"totalTokenCount":15}}\n'
        httpx_mock.add_response(
            stream=httpx.ByteStream(chunk.encode()),
        )
        events = []
        async for event in adapter.stream(
            Request(model="gemini-3-flash-preview", messages=[Message.user("Weather?")])
        ):
            events.append(event)

        types = [e.type for e in events]
        # Function calls come as complete TOOL_CALL_START + TOOL_CALL_END
        assert StreamEventType.TOOL_CALL_START in types
        assert StreamEventType.TOOL_CALL_END in types
        assert StreamEventType.FINISH in types
