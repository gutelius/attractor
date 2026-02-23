"""Provider adapter base interface."""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from attractor_llm.types import Request, Response, StreamEvent


@runtime_checkable
class ProviderAdapter(Protocol):
    """Interface that every provider adapter must implement."""

    @property
    def name(self) -> str:
        """Provider name, e.g. 'openai', 'anthropic', 'gemini'."""
        ...

    async def complete(self, request: Request) -> Response:
        """Send a request and return the full response."""
        ...

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        """Send a request and return an async iterator of stream events."""
        ...

    async def close(self) -> None:
        """Release resources (HTTP connections, etc.)."""
        ...

    async def initialize(self) -> None:
        """Validate configuration on startup."""
        ...

    def supports_tool_choice(self, mode: str) -> bool:
        """Query whether a particular tool choice mode is supported."""
        ...
