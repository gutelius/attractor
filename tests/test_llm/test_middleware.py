"""Tests for attractor_llm.middleware."""

import pytest
from attractor_llm.middleware import MiddlewareChain
from attractor_llm.types import (
    ContentKind,
    ContentPart,
    FinishReason,
    Message,
    Request,
    Response,
    Role,
    StreamEvent,
    StreamEventType,
    Usage,
)


class TestMiddlewareChain:
    @pytest.mark.asyncio
    async def test_no_middleware(self):
        chain = MiddlewareChain()
        req = Request(model="test", messages=[Message.user("Hi")])
        resp = Response(
            id="1", model="test", provider="test",
            message=Message.assistant("Hello"),
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2),
        )

        async def handler(r: Request) -> Response:
            return resp

        result = await chain.apply_complete(req, handler)
        assert result.text == "Hello"

    @pytest.mark.asyncio
    async def test_request_modification(self):
        """Middleware can modify the request before passing to next."""
        async def add_metadata(request, next_fn):
            request.metadata = {"traced": "true"}
            return await next_fn(request)

        chain = MiddlewareChain()
        chain.use(add_metadata)

        captured = {}

        async def handler(r: Request) -> Response:
            captured["metadata"] = r.metadata
            return Response(
                id="1", model="test", provider="test",
                message=Message.assistant("ok"),
                finish_reason=FinishReason(reason="stop"),
                usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2),
            )

        await chain.apply_complete(Request(model="test", messages=[]), handler)
        assert captured["metadata"] == {"traced": "true"}

    @pytest.mark.asyncio
    async def test_response_modification(self):
        """Middleware can modify the response on the way back."""
        async def tag_response(request, next_fn):
            resp = await next_fn(request)
            resp.raw = {"tagged": True}
            return resp

        chain = MiddlewareChain()
        chain.use(tag_response)

        async def handler(r: Request) -> Response:
            return Response(
                id="1", model="test", provider="test",
                message=Message.assistant("ok"),
                finish_reason=FinishReason(reason="stop"),
                usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2),
            )

        result = await chain.apply_complete(Request(model="test", messages=[]), handler)
        assert result.raw == {"tagged": True}

    @pytest.mark.asyncio
    async def test_ordering(self):
        """Middleware executes in registration order for request, reverse for response."""
        order = []

        async def mw1(request, next_fn):
            order.append("mw1_before")
            resp = await next_fn(request)
            order.append("mw1_after")
            return resp

        async def mw2(request, next_fn):
            order.append("mw2_before")
            resp = await next_fn(request)
            order.append("mw2_after")
            return resp

        chain = MiddlewareChain()
        chain.use(mw1)
        chain.use(mw2)

        async def handler(r: Request) -> Response:
            order.append("handler")
            return Response(
                id="1", model="test", provider="test",
                message=Message.assistant("ok"),
                finish_reason=FinishReason(reason="stop"),
                usage=Usage(input_tokens=1, output_tokens=1, total_tokens=2),
            )

        await chain.apply_complete(Request(model="test", messages=[]), handler)
        assert order == ["mw1_before", "mw2_before", "handler", "mw2_after", "mw1_after"]

    @pytest.mark.asyncio
    async def test_stream_middleware(self):
        """Middleware can wrap stream iterators."""
        collected_deltas = []

        async def logging_mw(request, next_fn):
            async def wrapped_stream():
                async for event in await next_fn(request):
                    if event.delta:
                        collected_deltas.append(event.delta)
                    yield event
            return wrapped_stream()

        chain = MiddlewareChain()
        chain.use_stream(logging_mw)

        async def handler(r: Request):
            async def gen():
                yield StreamEvent(type=StreamEventType.TEXT_DELTA, delta="Hello")
                yield StreamEvent(type=StreamEventType.TEXT_DELTA, delta=" world")
                yield StreamEvent(type=StreamEventType.FINISH)
            return gen()

        events = []
        async for event in await chain.apply_stream(Request(model="test", messages=[]), handler):
            events.append(event)

        assert len(events) == 3
        assert collected_deltas == ["Hello", " world"]
