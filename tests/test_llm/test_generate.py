"""Tests for attractor_llm.generate."""

import pytest
from unittest.mock import AsyncMock

from attractor_llm.client import Client
from attractor_llm.generate import generate, GenerateResult, StepResult
from attractor_llm.errors import ConfigurationError
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
    Usage,
)


def _text_response(text: str, usage: Usage | None = None) -> Response:
    return Response(
        id="resp_1",
        model="test",
        provider="test",
        message=Message.assistant(text),
        finish_reason=FinishReason(reason="stop"),
        usage=usage or Usage(input_tokens=10, output_tokens=5, total_tokens=15),
    )


def _tool_response(calls: list[dict], usage: Usage | None = None) -> Response:
    parts = []
    for c in calls:
        parts.append(ContentPart(
            kind=ContentKind.TOOL_CALL,
            tool_call=ToolCallData(id=c["id"], name=c["name"], arguments=c["args"]),
        ))
    return Response(
        id="resp_1",
        model="test",
        provider="test",
        message=Message(role=Role.ASSISTANT, content=parts),
        finish_reason=FinishReason(reason="tool_calls"),
        usage=usage or Usage(input_tokens=10, output_tokens=5, total_tokens=15),
    )


def _mock_client(responses: list[Response]) -> Client:
    adapter = AsyncMock()
    adapter.name = "test"
    adapter.close = AsyncMock()
    adapter.complete = AsyncMock(side_effect=responses)
    return Client(providers={"test": adapter}, default_provider="test")


class TestGenerate:
    @pytest.mark.asyncio
    async def test_simple_text(self):
        client = _mock_client([_text_response("Hello!")])
        result = await generate(model="test", prompt="Hi", client=client, provider="test")
        assert result.text == "Hello!"
        assert len(result.steps) == 1
        assert result.finish_reason.reason == "stop"

    @pytest.mark.asyncio
    async def test_with_messages(self):
        client = _mock_client([_text_response("World")])
        result = await generate(
            model="test",
            messages=[Message.user("Hello")],
            client=client,
            provider="test",
        )
        assert result.text == "World"

    @pytest.mark.asyncio
    async def test_rejects_prompt_and_messages(self):
        client = _mock_client([])
        with pytest.raises(ConfigurationError):
            await generate(
                model="test",
                prompt="Hi",
                messages=[Message.user("Hello")],
                client=client,
            )

    @pytest.mark.asyncio
    async def test_tool_execution_loop(self):
        """Tools are executed and results fed back to model."""
        def get_weather(city: str) -> str:
            return f"72F in {city}"

        tool = ToolDefinition(
            name="get_weather",
            description="Get weather",
            parameters={"type": "object", "properties": {"city": {"type": "string"}}},
            execute=get_weather,
        )

        responses = [
            _tool_response([{"id": "call_1", "name": "get_weather", "args": {"city": "SF"}}]),
            _text_response("It's 72F in SF."),
        ]
        client = _mock_client(responses)

        result = await generate(
            model="test",
            prompt="What's the weather in SF?",
            tools=[tool],
            max_tool_rounds=1,
            client=client,
            provider="test",
        )

        assert result.text == "It's 72F in SF."
        assert len(result.steps) == 2
        assert result.steps[0].tool_calls[0].name == "get_weather"
        assert result.steps[0].tool_results[0].content == "72F in SF"
        assert not result.steps[0].tool_results[0].is_error

    @pytest.mark.asyncio
    async def test_max_tool_rounds_zero(self):
        """max_tool_rounds=0 returns tool calls without executing."""
        tool = ToolDefinition(
            name="get_weather",
            description="Get weather",
            parameters={"type": "object"},
            execute=lambda: "result",
        )
        responses = [
            _tool_response([{"id": "call_1", "name": "get_weather", "args": {}}]),
        ]
        client = _mock_client(responses)

        result = await generate(
            model="test",
            prompt="weather?",
            tools=[tool],
            max_tool_rounds=0,
            client=client,
            provider="test",
        )

        assert len(result.tool_calls) == 1
        assert len(result.steps) == 1
        assert result.steps[0].tool_results == []  # Not executed

    @pytest.mark.asyncio
    async def test_total_usage_aggregation(self):
        responses = [
            _tool_response(
                [{"id": "c1", "name": "fn", "args": {}}],
                usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
            ),
            _text_response(
                "done",
                usage=Usage(input_tokens=20, output_tokens=10, total_tokens=30),
            ),
        ]
        tool = ToolDefinition(name="fn", description="d", parameters={"type": "object"}, execute=lambda: "ok")
        client = _mock_client(responses)

        result = await generate(
            model="test", prompt="go", tools=[tool], max_tool_rounds=1,
            client=client, provider="test",
        )

        assert result.total_usage.input_tokens == 30
        assert result.total_usage.output_tokens == 15
        assert result.total_usage.total_tokens == 45

    @pytest.mark.asyncio
    async def test_tool_error_handling(self):
        """Tool exceptions become error results."""
        def bad_tool() -> str:
            raise ValueError("oops")

        tool = ToolDefinition(name="bad", description="d", parameters={"type": "object"}, execute=bad_tool)
        responses = [
            _tool_response([{"id": "c1", "name": "bad", "args": {}}]),
            _text_response("recovered"),
        ]
        client = _mock_client(responses)

        result = await generate(
            model="test", prompt="go", tools=[tool], max_tool_rounds=1,
            client=client, provider="test",
        )

        assert result.steps[0].tool_results[0].is_error
        assert "oops" in result.steps[0].tool_results[0].content

    @pytest.mark.asyncio
    async def test_system_message(self):
        client = _mock_client([_text_response("Hello")])
        result = await generate(
            model="test", prompt="Hi", system="Be helpful.",
            client=client, provider="test",
        )
        # Verify system message was included
        adapter = list(client.providers.values())[0]
        call_args = adapter.complete.call_args[0][0]
        assert call_args.messages[0].role == Role.SYSTEM
        assert call_args.messages[0].text == "Be helpful."
