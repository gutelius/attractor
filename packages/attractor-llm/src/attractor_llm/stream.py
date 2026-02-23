"""High-level stream() API and StreamAccumulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator

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
    ToolCall,
    ToolCallData,
    Usage,
)


class StreamAccumulator:
    """Collects stream events into a complete Response."""

    def __init__(self) -> None:
        self._text_parts: list[str] = []
        self._reasoning_parts: list[str] = []
        self._tool_calls: list[ToolCall] = []
        self._current_tool: dict[str, Any] | None = None
        self._finish_reason: FinishReason | None = None
        self._usage: Usage | None = None
        self._response: Response | None = None

    def process(self, event: StreamEvent) -> None:
        """Process a single stream event."""
        if event.type == StreamEventType.TEXT_DELTA and event.delta:
            self._text_parts.append(event.delta)
        elif event.type == StreamEventType.REASONING_DELTA and event.reasoning_delta:
            self._reasoning_parts.append(event.reasoning_delta)
        elif event.type == StreamEventType.TOOL_CALL_START and event.tool_call:
            self._current_tool = {
                "id": event.tool_call.id,
                "name": event.tool_call.name,
                "args_parts": [],
            }
        elif event.type == StreamEventType.TOOL_CALL_DELTA and event.delta:
            if self._current_tool:
                self._current_tool["args_parts"].append(event.delta)
        elif event.type == StreamEventType.TOOL_CALL_END:
            if event.tool_call:
                self._tool_calls.append(event.tool_call)
            elif self._current_tool:
                import json
                args_str = "".join(self._current_tool["args_parts"])
                try:
                    args = json.loads(args_str) if args_str else {}
                except json.JSONDecodeError:
                    args = {}
                self._tool_calls.append(ToolCall(
                    id=self._current_tool["id"],
                    name=self._current_tool["name"],
                    arguments=args,
                ))
            self._current_tool = None
        elif event.type == StreamEventType.FINISH:
            self._finish_reason = event.finish_reason
            self._usage = event.usage
            if event.response:
                self._response = event.response

    @property
    def text(self) -> str:
        return "".join(self._text_parts)

    @property
    def reasoning(self) -> str | None:
        return "".join(self._reasoning_parts) if self._reasoning_parts else None

    def response(self) -> Response:
        """Build the accumulated Response."""
        if self._response:
            return self._response

        content_parts: list[ContentPart] = []
        if self._text_parts:
            content_parts.append(
                ContentPart(kind=ContentKind.TEXT, text=self.text)
            )
        for tc in self._tool_calls:
            content_parts.append(
                ContentPart(
                    kind=ContentKind.TOOL_CALL,
                    tool_call=ToolCallData(
                        id=tc.id,
                        name=tc.name,
                        arguments=tc.arguments,
                    ),
                )
            )

        return Response(
            id="",
            model="",
            provider="",
            message=Message(role=Role.ASSISTANT, content=content_parts),
            finish_reason=self._finish_reason or FinishReason(reason="stop"),
            usage=self._usage or Usage(),
        )


class StreamResult:
    """Wraps an async stream with convenience accessors."""

    def __init__(self, event_iter: AsyncIterator[StreamEvent]) -> None:
        self._iter = event_iter
        self._accumulator = StreamAccumulator()
        self._done = False

    async def __aiter__(self) -> AsyncIterator[StreamEvent]:
        async for event in self._iter:
            self._accumulator.process(event)
            yield event
        self._done = True

    @property
    def text_stream(self) -> AsyncIterator[str]:
        """Yields only text deltas."""
        return self._text_stream_gen()

    async def _text_stream_gen(self) -> AsyncIterator[str]:
        async for event in self._iter:
            self._accumulator.process(event)
            if event.type == StreamEventType.TEXT_DELTA and event.delta:
                yield event.delta
        self._done = True

    def response(self) -> Response:
        """Get accumulated response (available after stream ends)."""
        return self._accumulator.response()

    @property
    def partial_response(self) -> Response | None:
        """Current accumulated state."""
        return self._accumulator.response()


async def stream(
    model: str,
    prompt: str | None = None,
    messages: list[Message] | None = None,
    system: str | None = None,
    tools: list[Any] | None = None,
    tool_choice: Any | None = None,
    provider: str | None = None,
    provider_options: dict[str, Any] | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    client: Any = None,
) -> StreamResult:
    """High-level streaming generation."""
    from attractor_llm.errors import ConfigurationError

    if prompt is not None and messages is not None:
        raise ConfigurationError("Cannot specify both 'prompt' and 'messages'")

    conversation: list[Message] = []
    if system:
        conversation.append(Message.system(system))
    if messages:
        conversation.extend(messages)
    elif prompt is not None:
        conversation.append(Message.user(prompt))

    if client is None:
        from attractor_llm.client import get_default_client
        client = get_default_client()

    request = Request(
        model=model,
        messages=conversation,
        provider=provider,
        tools=tools,
        tool_choice=tool_choice,
        temperature=temperature,
        top_p=top_p,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        provider_options=provider_options,
    )

    event_iter = await client.stream(request)
    return StreamResult(event_iter)
