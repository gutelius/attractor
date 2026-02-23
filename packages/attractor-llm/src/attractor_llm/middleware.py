"""Middleware chain for request/response interception."""

from __future__ import annotations

from typing import Any, AsyncIterator, Awaitable, Callable

from attractor_llm.types import Request, Response, StreamEvent

# Middleware signature: async (request, next_fn) -> Response
CompleteMiddleware = Callable[
    [Request, Callable[[Request], Awaitable[Response]]],
    Awaitable[Response],
]

# Stream middleware: async (request, next_fn) -> AsyncIterator[StreamEvent]
StreamMiddleware = Callable[
    [Request, Callable[[Request], Awaitable[Any]]],
    Awaitable[Any],
]


class MiddlewareChain:
    """Onion/chain-of-responsibility middleware for complete and stream calls."""

    def __init__(self) -> None:
        self._complete_mw: list[CompleteMiddleware] = []
        self._stream_mw: list[StreamMiddleware] = []

    def use(self, middleware: CompleteMiddleware) -> None:
        """Register middleware for complete() calls."""
        self._complete_mw.append(middleware)

    def use_stream(self, middleware: StreamMiddleware) -> None:
        """Register middleware for stream() calls."""
        self._stream_mw.append(middleware)

    async def apply_complete(
        self,
        request: Request,
        handler: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        """Apply middleware chain and call handler."""
        chain = handler
        # Build from inside out (last registered wraps closest to handler)
        for mw in reversed(self._complete_mw):
            chain = _wrap_complete(mw, chain)
        return await chain(request)

    async def apply_stream(
        self,
        request: Request,
        handler: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        """Apply stream middleware chain and call handler."""
        chain = handler
        for mw in reversed(self._stream_mw):
            chain = _wrap_stream(mw, chain)
        return await chain(request)


def _wrap_complete(
    mw: CompleteMiddleware,
    next_fn: Callable[[Request], Awaitable[Response]],
) -> Callable[[Request], Awaitable[Response]]:
    async def wrapped(request: Request) -> Response:
        return await mw(request, next_fn)
    return wrapped


def _wrap_stream(
    mw: StreamMiddleware,
    next_fn: Callable[[Request], Awaitable[Any]],
) -> Callable[[Request], Awaitable[Any]]:
    async def wrapped(request: Request) -> Any:
        return await mw(request, next_fn)
    return wrapped
