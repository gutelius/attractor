"""Anthropic provider adapter using the Messages API."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from attractor_llm.errors import (
    AuthenticationError,
    AccessDeniedError,
    ContextLengthError,
    ContentFilterError,
    InvalidRequestError,
    NotFoundError,
    RateLimitError,
    ServerError,
    classify_error_message,
)
from attractor_llm.types import (
    ContentKind,
    ContentPart,
    FinishReason,
    Message,
    RateLimitInfo,
    Request,
    Response,
    Role,
    StreamEvent,
    StreamEventType,
    ThinkingData,
    ToolCall,
    ToolCallData,
    ToolResultData,
    Usage,
)

_STATUS_MAP: dict[int, type] = {
    400: InvalidRequestError,
    401: AuthenticationError,
    403: AccessDeniedError,
    404: NotFoundError,
    413: ContextLengthError,
    422: InvalidRequestError,
    429: RateLimitError,
    500: ServerError,
    502: ServerError,
    503: ServerError,
    504: ServerError,
}

_FINISH_MAP: dict[str, str] = {
    "end_turn": "stop",
    "stop_sequence": "stop",
    "max_tokens": "length",
    "tool_use": "tool_calls",
}


class AnthropicAdapter:
    """Adapter for the Anthropic Messages API (/v1/messages)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        api_version: str = "2023-06-01",
        http_client: httpx.AsyncClient | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._api_version = api_version
        self._client = http_client or httpx.AsyncClient(
            headers={
                "x-api-key": api_key,
                "anthropic-version": api_version,
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(300.0),
        )

    @property
    def name(self) -> str:
        return "anthropic"

    async def complete(self, request: Request) -> Response:
        body, headers = self._build_request(request, stream=False)
        http_resp = await self._client.post(
            f"{self._base_url}/v1/messages", json=body, headers=headers
        )
        if http_resp.status_code >= 400:
            self._raise_error(http_resp)
        return self._parse_response(http_resp.json(), http_resp)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        body, headers = self._build_request(request, stream=True)
        async with self._client.stream(
            "POST", f"{self._base_url}/v1/messages", json=body, headers=headers
        ) as http_resp:
            if http_resp.status_code >= 400:
                await http_resp.aread()
                self._raise_error(http_resp)
            async for event in self._parse_sse_stream(http_resp):
                yield event

    async def close(self) -> None:
        await self._client.aclose()

    async def initialize(self) -> None:
        pass

    def supports_tool_choice(self, mode: str) -> bool:
        return mode in ("auto", "none", "required", "named")

    # -- Request building --

    def _build_request(
        self, request: Request, *, stream: bool
    ) -> tuple[dict[str, Any], dict[str, str]]:
        body: dict[str, Any] = {"model": request.model}
        extra_headers: dict[str, str] = {}

        # Extract system messages
        system_parts, api_messages = self._translate_messages(request.messages)
        if system_parts:
            body["system"] = system_parts
        body["messages"] = api_messages

        # max_tokens is required
        body["max_tokens"] = request.max_tokens or 4096

        if stream:
            body["stream"] = True

        if request.tools and (not request.tool_choice or request.tool_choice.mode != "none"):
            body["tools"] = [self._translate_tool(t) for t in request.tools]

        if request.tool_choice:
            tc = self._translate_tool_choice(request.tool_choice)
            if tc is not None:
                body["tool_choice"] = tc

        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.stop_sequences:
            body["stop_sequences"] = request.stop_sequences

        # Provider options
        opts = (request.provider_options or {}).get("anthropic", {})
        beta_headers = opts.pop("beta_headers", None)
        if beta_headers:
            extra_headers["anthropic-beta"] = ",".join(beta_headers)
        # Apply remaining options
        for k, v in opts.items():
            body[k] = v

        return body, extra_headers

    def _translate_messages(
        self, messages: list[Message]
    ) -> tuple[list[dict[str, Any]] | str, list[dict[str, Any]]]:
        system_parts: list[dict[str, Any]] = []
        api_messages: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role in (Role.SYSTEM, Role.DEVELOPER):
                for p in msg.content:
                    if p.text:
                        system_parts.append({"type": "text", "text": p.text})
                continue

            if msg.role == Role.TOOL:
                # Tool results go in user messages
                blocks: list[dict[str, Any]] = []
                for p in msg.content:
                    if p.kind == ContentKind.TOOL_RESULT and p.tool_result:
                        content = p.tool_result.content
                        if isinstance(content, dict):
                            content = json.dumps(content)
                        block: dict[str, Any] = {
                            "type": "tool_result",
                            "tool_use_id": p.tool_result.tool_call_id,
                            "content": str(content),
                        }
                        if p.tool_result.is_error:
                            block["is_error"] = True
                        blocks.append(block)
                if blocks:
                    self._append_message(api_messages, "user", blocks)
                continue

            role = "user" if msg.role == Role.USER else "assistant"
            content_blocks: list[dict[str, Any]] = []

            for p in msg.content:
                if p.kind == ContentKind.TEXT and p.text is not None:
                    content_blocks.append({"type": "text", "text": p.text})
                elif p.kind == ContentKind.TOOL_CALL and p.tool_call:
                    args = p.tool_call.arguments
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    content_blocks.append({
                        "type": "tool_use",
                        "id": p.tool_call.id,
                        "name": p.tool_call.name,
                        "input": args,
                    })
                elif p.kind == ContentKind.THINKING and p.thinking:
                    block = {
                        "type": "thinking",
                        "thinking": p.thinking.text,
                    }
                    if p.thinking.signature:
                        block["signature"] = p.thinking.signature
                    content_blocks.append(block)
                elif p.kind == ContentKind.REDACTED_THINKING and p.thinking:
                    content_blocks.append({
                        "type": "redacted_thinking",
                        "data": p.thinking.text,
                    })
                elif p.kind == ContentKind.IMAGE and p.image:
                    if p.image.url:
                        content_blocks.append({
                            "type": "image",
                            "source": {"type": "url", "url": p.image.url},
                        })
                    elif p.image.data:
                        import base64
                        content_blocks.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": p.image.media_type or "image/png",
                                "data": base64.b64encode(p.image.data).decode(),
                            },
                        })

            if content_blocks:
                self._append_message(api_messages, role, content_blocks)

        # Return system as string if single text, else as list
        if len(system_parts) == 1 and system_parts[0].get("type") == "text":
            return system_parts[0]["text"], api_messages
        return system_parts if system_parts else "", api_messages

    def _append_message(
        self,
        messages: list[dict[str, Any]],
        role: str,
        content: list[dict[str, Any]],
    ) -> None:
        """Append message, merging with previous if same role (strict alternation)."""
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"].extend(content)
        else:
            messages.append({"role": role, "content": content})

    def _translate_tool(self, tool: Any) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
        }

    def _translate_tool_choice(self, tc: Any) -> dict[str, Any] | None:
        if tc.mode == "auto":
            return {"type": "auto"}
        if tc.mode == "none":
            return None  # Omit tools entirely
        if tc.mode == "required":
            return {"type": "any"}
        if tc.mode == "named":
            return {"type": "tool", "name": tc.tool_name}
        return {"type": "auto"}

    # -- Response parsing --

    def _parse_response(
        self, data: dict[str, Any], http_resp: httpx.Response | None = None
    ) -> Response:
        content_parts: list[ContentPart] = []

        for block in data.get("content", []):
            block_type = block.get("type", "")
            if block_type == "text":
                content_parts.append(
                    ContentPart(kind=ContentKind.TEXT, text=block.get("text", ""))
                )
            elif block_type == "tool_use":
                content_parts.append(
                    ContentPart(
                        kind=ContentKind.TOOL_CALL,
                        tool_call=ToolCallData(
                            id=block.get("id", ""),
                            name=block.get("name", ""),
                            arguments=block.get("input", {}),
                        ),
                    )
                )
            elif block_type == "thinking":
                content_parts.append(
                    ContentPart(
                        kind=ContentKind.THINKING,
                        thinking=ThinkingData(
                            text=block.get("thinking", ""),
                            signature=block.get("signature"),
                            redacted=False,
                        ),
                    )
                )
            elif block_type == "redacted_thinking":
                content_parts.append(
                    ContentPart(
                        kind=ContentKind.REDACTED_THINKING,
                        thinking=ThinkingData(
                            text=block.get("data", ""),
                            redacted=True,
                        ),
                    )
                )

        msg = Message(role=Role.ASSISTANT, content=content_parts)

        # Finish reason
        raw_reason = data.get("stop_reason", "end_turn")
        reason = _FINISH_MAP.get(raw_reason, "other")
        fr = FinishReason(reason=reason, raw=raw_reason)

        # Usage
        usage_data = data.get("usage", {})
        usage = Usage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("input_tokens", 0) + usage_data.get("output_tokens", 0),
            cache_read_tokens=usage_data.get("cache_read_input_tokens"),
            cache_write_tokens=usage_data.get("cache_creation_input_tokens"),
            raw=usage_data or None,
        )

        rate_limit = None
        if http_resp:
            rate_limit = self._parse_rate_limit(http_resp.headers)

        return Response(
            id=data.get("id", ""),
            model=data.get("model", ""),
            provider="anthropic",
            message=msg,
            finish_reason=fr,
            usage=usage,
            raw=data,
            rate_limit=rate_limit,
        )

    def _parse_rate_limit(self, headers: httpx.Headers) -> RateLimitInfo | None:
        def _int(key: str) -> int | None:
            v = headers.get(key)
            return int(v) if v else None

        rli = RateLimitInfo(
            requests_remaining=_int("anthropic-ratelimit-requests-remaining"),
            requests_limit=_int("anthropic-ratelimit-requests-limit"),
            tokens_remaining=_int("anthropic-ratelimit-tokens-remaining"),
            tokens_limit=_int("anthropic-ratelimit-tokens-limit"),
        )
        if any(
            v is not None
            for v in (rli.requests_remaining, rli.requests_limit, rli.tokens_remaining, rli.tokens_limit)
        ):
            return rli
        return None

    # -- Streaming --

    async def _parse_sse_stream(
        self, http_resp: httpx.Response
    ) -> AsyncIterator[StreamEvent]:
        current_block_type: str | None = None
        current_block_id: str | None = None
        current_tool_name: str | None = None
        accumulated_args: str = ""
        input_tokens = 0
        output_tokens = 0

        async for line in http_resp.aiter_lines():
            if not line or line.startswith(":"):
                continue
            if line.startswith("event: "):
                event_type = line[7:].strip()
                continue
            if not line.startswith("data: "):
                continue

            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type", "")

            if msg_type == "message_start":
                msg_data = data.get("message", {})
                usage = msg_data.get("usage", {})
                input_tokens = usage.get("input_tokens", 0)
                yield StreamEvent(type=StreamEventType.STREAM_START)

            elif msg_type == "content_block_start":
                block = data.get("content_block", {})
                block_type = block.get("type", "")
                current_block_type = block_type

                if block_type == "text":
                    yield StreamEvent(type=StreamEventType.TEXT_START)
                elif block_type == "tool_use":
                    current_block_id = block.get("id", "")
                    current_tool_name = block.get("name", "")
                    accumulated_args = ""
                    yield StreamEvent(
                        type=StreamEventType.TOOL_CALL_START,
                        tool_call=ToolCall(
                            id=current_block_id,
                            name=current_tool_name,
                        ),
                    )
                elif block_type == "thinking":
                    yield StreamEvent(type=StreamEventType.REASONING_START)

            elif msg_type == "content_block_delta":
                delta = data.get("delta", {})
                delta_type = delta.get("type", "")

                if delta_type == "text_delta":
                    yield StreamEvent(
                        type=StreamEventType.TEXT_DELTA,
                        delta=delta.get("text", ""),
                    )
                elif delta_type == "input_json_delta":
                    partial = delta.get("partial_json", "")
                    accumulated_args += partial
                    yield StreamEvent(
                        type=StreamEventType.TOOL_CALL_DELTA,
                        delta=partial,
                    )
                elif delta_type == "thinking_delta":
                    yield StreamEvent(
                        type=StreamEventType.REASONING_DELTA,
                        reasoning_delta=delta.get("thinking", ""),
                    )

            elif msg_type == "content_block_stop":
                if current_block_type == "text":
                    yield StreamEvent(type=StreamEventType.TEXT_END)
                elif current_block_type == "tool_use":
                    try:
                        args = json.loads(accumulated_args) if accumulated_args else {}
                    except json.JSONDecodeError:
                        args = {}
                    yield StreamEvent(
                        type=StreamEventType.TOOL_CALL_END,
                        tool_call=ToolCall(
                            id=current_block_id or "",
                            name=current_tool_name or "",
                            arguments=args,
                        ),
                    )
                elif current_block_type == "thinking":
                    yield StreamEvent(type=StreamEventType.REASONING_END)
                current_block_type = None

            elif msg_type == "message_delta":
                delta = data.get("delta", {})
                usage = data.get("usage", {})
                output_tokens = usage.get("output_tokens", 0)
                raw_reason = delta.get("stop_reason", "end_turn")
                reason = _FINISH_MAP.get(raw_reason, "other")
                # Don't yield FINISH here, wait for message_stop

            elif msg_type == "message_stop":
                yield StreamEvent(
                    type=StreamEventType.FINISH,
                    usage=Usage(
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        total_tokens=input_tokens + output_tokens,
                    ),
                )

    # -- Error handling --

    def _raise_error(self, http_resp: httpx.Response) -> None:
        try:
            body = http_resp.json()
        except Exception:
            body = {"error": {"message": http_resp.text}}

        error_obj = body.get("error", {})
        message = error_obj.get("message", http_resp.text)
        error_code = error_obj.get("type")

        retry_after = None
        ra_header = http_resp.headers.get("retry-after")
        if ra_header:
            try:
                retry_after = float(ra_header)
            except ValueError:
                pass

        status = http_resp.status_code
        err_cls = _STATUS_MAP.get(status, ServerError)

        # Refine with message classification
        classification = classify_error_message(message)
        if classification == "context_length":
            err_cls = ContextLengthError
        elif classification == "content_filter":
            err_cls = ContentFilterError

        raise err_cls(
            message,
            provider="anthropic",
            error_code=error_code,
            raw=body,
            retry_after=retry_after,
        )
