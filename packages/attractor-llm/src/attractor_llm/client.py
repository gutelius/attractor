"""Unified LLM client with provider routing and middleware."""

from __future__ import annotations

import os
from typing import Any, AsyncIterator

from attractor_llm.errors import ConfigurationError
from attractor_llm.middleware import MiddlewareChain
from attractor_llm.types import Request, Response, StreamEvent

# Lazy-initialized module-level default client
_default_client: Client | None = None


class Client:
    """Unified client routing requests to provider adapters."""

    def __init__(
        self,
        providers: dict[str, Any],
        default_provider: str | None = None,
    ):
        if not providers:
            raise ConfigurationError("At least one provider must be configured")

        self._providers = providers
        self._default_provider = default_provider or next(iter(providers))
        self._middleware = MiddlewareChain()

    @property
    def providers(self) -> dict[str, Any]:
        return dict(self._providers)

    @property
    def default_provider(self) -> str:
        return self._default_provider

    @classmethod
    def from_env(cls) -> Client:
        """Auto-detect providers from environment variables."""
        providers: dict[str, Any] = {}

        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            from attractor_llm.providers.openai import OpenAIAdapter
            base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
            providers["openai"] = OpenAIAdapter(api_key=openai_key, base_url=base_url)

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            from attractor_llm.providers.anthropic import AnthropicAdapter
            base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
            providers["anthropic"] = AnthropicAdapter(api_key=anthropic_key, base_url=base_url)

        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if gemini_key:
            from attractor_llm.providers.gemini import GeminiAdapter
            base_url = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com")
            providers["gemini"] = GeminiAdapter(api_key=gemini_key, base_url=base_url)

        if not providers:
            raise ConfigurationError(
                "No provider API keys found. Set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY."
            )

        return cls(providers=providers)

    def use(self, middleware: Any) -> None:
        """Register middleware for complete() calls."""
        self._middleware.use(middleware)

    def use_stream(self, middleware: Any) -> None:
        """Register middleware for stream() calls."""
        self._middleware.use_stream(middleware)

    async def complete(self, request: Request) -> Response:
        """Send a request and return the full response."""
        adapter = self._resolve_adapter(request)

        async def handler(req: Request) -> Response:
            return await adapter.complete(req)

        return await self._middleware.apply_complete(request, handler)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Send a request and return an async iterator of stream events."""
        adapter = self._resolve_adapter(request)

        async def handler(req: Request) -> AsyncIterator[StreamEvent]:
            return adapter.stream(req)

        return await self._middleware.apply_stream(request, handler)

    async def close(self) -> None:
        """Close all provider adapters."""
        for adapter in self._providers.values():
            await adapter.close()

    def _resolve_adapter(self, request: Request) -> Any:
        provider = request.provider or self._default_provider
        if provider not in self._providers:
            raise ConfigurationError(
                f"Provider '{provider}' not configured. "
                f"Available: {list(self._providers.keys())}"
            )
        return self._providers[provider]


def get_default_client() -> Client:
    """Get or lazily initialize the module-level default client."""
    global _default_client
    if _default_client is None:
        _default_client = Client.from_env()
    return _default_client


def set_default_client(client: Client) -> None:
    """Override the module-level default client."""
    global _default_client
    _default_client = client
