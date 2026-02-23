"""Tests for attractor_llm.client."""

import os
import pytest
from unittest.mock import AsyncMock, patch

from attractor_llm.client import Client
from attractor_llm.errors import ConfigurationError
from attractor_llm.types import (
    FinishReason,
    Message,
    Request,
    Response,
    StreamEvent,
    StreamEventType,
    Usage,
)


def _make_mock_adapter(name: str = "test") -> AsyncMock:
    adapter = AsyncMock()
    adapter.name = name
    adapter.complete = AsyncMock(
        return_value=Response(
            id="resp_1",
            model="test-model",
            provider=name,
            message=Message.assistant("Hello"),
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=5, output_tokens=3, total_tokens=8),
        )
    )

    async def mock_stream(request):
        yield StreamEvent(type=StreamEventType.TEXT_DELTA, delta="Hello")
        yield StreamEvent(type=StreamEventType.FINISH)

    adapter.stream = AsyncMock(side_effect=mock_stream)
    adapter.close = AsyncMock()
    adapter.initialize = AsyncMock()
    return adapter


class TestClientConstruction:
    def test_programmatic(self):
        adapter = _make_mock_adapter("openai")
        client = Client(providers={"openai": adapter}, default_provider="openai")
        assert client.default_provider == "openai"

    def test_no_providers_raises(self):
        with pytest.raises(ConfigurationError):
            Client(providers={})

    def test_first_provider_becomes_default(self):
        a1 = _make_mock_adapter("openai")
        a2 = _make_mock_adapter("anthropic")
        client = Client(providers={"openai": a1, "anthropic": a2})
        assert client.default_provider == "openai"


class TestClientFromEnv:
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=False)
    def test_detects_openai(self):
        client = Client.from_env()
        assert "openai" in client.providers

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}, clear=False)
    def test_detects_anthropic(self):
        client = Client.from_env()
        assert "anthropic" in client.providers

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}, clear=False)
    def test_detects_gemini(self):
        client = Client.from_env()
        assert "gemini" in client.providers

    @patch.dict(os.environ, {}, clear=True)
    def test_no_keys_raises(self):
        # Clear all API keys
        for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"]:
            os.environ.pop(key, None)
        with pytest.raises(ConfigurationError):
            Client.from_env()


class TestProviderRouting:
    @pytest.mark.asyncio
    async def test_explicit_provider(self):
        openai = _make_mock_adapter("openai")
        anthropic = _make_mock_adapter("anthropic")
        client = Client(providers={"openai": openai, "anthropic": anthropic})

        req = Request(model="claude-opus-4-6", messages=[Message.user("Hi")], provider="anthropic")
        await client.complete(req)
        anthropic.complete.assert_called_once()
        openai.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_provider_fallback(self):
        adapter = _make_mock_adapter("openai")
        client = Client(providers={"openai": adapter}, default_provider="openai")

        req = Request(model="gpt-5.2", messages=[Message.user("Hi")])
        resp = await client.complete(req)
        assert resp.provider == "openai"

    @pytest.mark.asyncio
    async def test_unknown_provider_raises(self):
        adapter = _make_mock_adapter("openai")
        client = Client(providers={"openai": adapter})

        req = Request(model="test", messages=[Message.user("Hi")], provider="unknown")
        with pytest.raises(ConfigurationError):
            await client.complete(req)


class TestClientMiddleware:
    @pytest.mark.asyncio
    async def test_middleware_applied(self):
        adapter = _make_mock_adapter("openai")
        client = Client(providers={"openai": adapter})

        called = []

        async def logging_mw(request, next_fn):
            called.append("before")
            resp = await next_fn(request)
            called.append("after")
            return resp

        client.use(logging_mw)

        req = Request(model="gpt-5.2", messages=[Message.user("Hi")])
        await client.complete(req)
        assert called == ["before", "after"]


class TestClientClose:
    @pytest.mark.asyncio
    async def test_close_all_adapters(self):
        a1 = _make_mock_adapter("openai")
        a2 = _make_mock_adapter("anthropic")
        client = Client(providers={"openai": a1, "anthropic": a2})
        await client.close()
        a1.close.assert_called_once()
        a2.close.assert_called_once()
