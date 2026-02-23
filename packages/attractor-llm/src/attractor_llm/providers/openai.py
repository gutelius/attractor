"""OpenAI provider adapter using the Responses API."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from attractor_llm.errors import (
    AuthenticationError,
    AccessDeniedError,
    ContextLengthError,
    InvalidRequestError,
    NotFoundError,
    RateLimitError,
    ServerError,
    NetworkError,
    StreamError,
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
    ToolCall,
    ToolCallData,
    ThinkingData,
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


class OpenAIAdapter:
    """Adapter for the OpenAI Responses API (/v1/responses)."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com",
        http_client: httpx.AsyncClient | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = http_client or httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(300.0),
        )

    @property
    def name(self) -> str:
        return "openai"

    async def complete(self, request: Request) -> Response:
        body = self._build_request_body(request, stream=False)
        http_resp = await self._client.post(
            f"{self._base_url}/v1/responses", json=body
        )
        if http_resp.status_code >= 400:
            self._raise_error(http_resp)
        data = http_resp.json()
        return self._parse_response(data, http_resp)

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        body = self._build_request_body(request, stream=True)
        async with self._client.stream(
            "POST", f"{self._base_url}/v1/responses", json=body
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

    def _build_request_body(self, request: Request, *, stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {"model": request.model}

        instructions, input_items = self._translate_messages(request.messages)
        if instructions:
            body["instructions"] = instructions
        body["input"] = input_items

        if stream:
            body["stream"] = True

        if request.tools:
            body["tools"] = [self._translate_tool(t) for t in request.tools]

        if request.tool_choice:
            body["tool_choice"] = self._translate_tool_choice(request.tool_choice)

        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.max_tokens is not None:
            body["max_output_tokens"] = request.max_tokens
        if request.stop_sequences:
            body["stop"] = request.stop_sequences
        if request.reasoning_effort:
            body["reasoning"] = {"effort": request.reasoning_effort}
        if request.response_format:
            if request.response_format.type == "json_schema" and request.response_format.json_schema:
                body["text"] = {
                    "format": {
                        "type": "json_schema",
                        "schema": request.response_format.json_schema,
                        "strict": request.response_format.strict,
                    }
                }
            elif request.response_format.type == "json":
                body["text"] = {"format": {"type": "json_object"}}

        # Apply provider options
        opts = (request.provider_options or {}).get("openai", {})
        for k, v in opts.items():
            body[k] = v

        return body

    def _translate_messages(
        self, messages: list[Message]
    ) -> tuple[str, list[dict[str, Any]]]:
        instructions_parts: list[str] = []
        items: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role in (Role.SYSTEM, Role.DEVELOPER):
                for p in msg.content:
                    if p.text:
                        instructions_parts.append(p.text)
                continue

            if msg.role == Role.TOOL:
                for p in msg.content:
                    if p.kind == ContentKind.TOOL_RESULT and p.tool_result:
                        content = p.tool_result.content
                        if not isinstance(content, str):
                            content = json.dumps(content)
                        items.append({
                            "type": "function_call_output",
                            "call_id": p.tool_result.tool_call_id,
                            "output": content,
                        })
                continue

            # USER or ASSISTANT
            role = "user" if msg.role == Role.USER else "assistant"
            content_parts: list[dict[str, Any]] = []

            for p in msg.content:
                if p.kind == ContentKind.TEXT and p.text is not None:
                    text_type = "input_text" if role == "user" else "output_text"
                    content_parts.append({"type": text_type, "text": p.text})
                elif p.kind == ContentKind.TOOL_CALL and p.tool_call:
                    args = p.tool_call.arguments
                    if isinstance(args, dict):
                        args = json.dumps(args)
                    items.append({
                        "type": "function_call",
                        "id": p.tool_call.id,
                        "call_id": p.tool_call.id,
                        "name": p.tool_call.name,
                        "arguments": args,
                    })
                    continue
                elif p.kind == ContentKind.IMAGE and p.image:
                    if p.image.url:
                        content_parts.append({
                            "type": "input_image",
                            "image_url": p.image.url,
                        })
                    elif p.image.data:
                        import base64
                        mt = p.image.media_type or "image/png"
                        b64 = base64.b64encode(p.image.data).decode()
                        content_parts.append({
                            "type": "input_image",
                            "image_url": f"data:{mt};base64,{b64}",
                        })

            if content_parts:
                items.append({
                    "type": "message",
                    "role": role,
                    "content": content_parts,
                })

        return "\n\n".join(instructions_parts), items

    def _translate_tool(self, tool: Any) -> dict[str, Any]:
        return {
            "type": "function",
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }

    def _translate_tool_choice(self, tc: Any) -> Any:
        if tc.mode == "auto":
            return "auto"
        if tc.mode == "none":
            return "none"
        if tc.mode == "required":
            return "required"
        if tc.mode == "named":
            return {"type": "function", "name": tc.tool_name}
        return "auto"

    # -- Response parsing --

    def _parse_response(
        self, data: dict[str, Any], http_resp: httpx.Response | None = None
    ) -> Response:
        content_parts: list[ContentPart] = []
        output = data.get("output", [])

        for item in output:
            item_type = item.get("type", "")
            if item_type == "message":
                for c in item.get("content", []):
                    if c.get("type") in ("output_text", "text"):
                        content_parts.append(
                            ContentPart(kind=ContentKind.TEXT, text=c.get("text", ""))
                        )
            elif item_type == "function_call":
                args_str = item.get("arguments", "{}")
                try:
                    args = json.loads(args_str) if isinstance(args_str, str) else args_str
                except json.JSONDecodeError:
                    args = {}
                content_parts.append(
                    ContentPart(
                        kind=ContentKind.TOOL_CALL,
                        tool_call=ToolCallData(
                            id=item.get("call_id", item.get("id", "")),
                            name=item.get("name", ""),
                            arguments=args,
                        ),
                    )
                )
            elif item_type == "reasoning":
                text = ""
                for s in item.get("summary", []):
                    text += s.get("text", "")
                if text:
                    content_parts.append(
                        ContentPart(
                            kind=ContentKind.THINKING,
                            thinking=ThinkingData(text=text, redacted=False),
                        )
                    )

        msg = Message(role=Role.ASSISTANT, content=content_parts)

        # Finish reason
        status = data.get("status", "completed")
        has_tool_calls = any(
            p.kind == ContentKind.TOOL_CALL for p in content_parts
        )
        if has_tool_calls:
            fr = FinishReason(reason="tool_calls", raw=status)
        elif status == "completed":
            fr = FinishReason(reason="stop", raw=status)
        elif status == "incomplete":
            fr = FinishReason(reason="length", raw=status)
        else:
            fr = FinishReason(reason="other", raw=status)

        # Usage
        usage_data = data.get("usage", {})
        reasoning_tokens = None
        output_details = usage_data.get("output_tokens_details", {})
        if output_details and output_details.get("reasoning_tokens"):
            reasoning_tokens = output_details["reasoning_tokens"]

        cache_read = None
        input_details = usage_data.get("input_tokens_details", {})
        if input_details and input_details.get("cached_tokens"):
            cache_read = input_details["cached_tokens"]

        usage = Usage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            reasoning_tokens=reasoning_tokens,
            cache_read_tokens=cache_read,
            raw=usage_data or None,
        )

        rate_limit = None
        if http_resp:
            rate_limit = self._parse_rate_limit(http_resp.headers)

        return Response(
            id=data.get("id", ""),
            model=data.get("model", ""),
            provider="openai",
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
            requests_remaining=_int("x-ratelimit-remaining-requests"),
            requests_limit=_int("x-ratelimit-limit-requests"),
            tokens_remaining=_int("x-ratelimit-remaining-tokens"),
            tokens_limit=_int("x-ratelimit-limit-tokens"),
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
        text_started = False
        accumulated_data: dict[str, Any] = {}

        async for line in http_resp.aiter_lines():
            if not line or line.startswith(":"):
                continue
            if line == "data: [DONE]":
                break
            if line.startswith("event: "):
                continue
            if line.startswith("data: "):
                raw_data = line[6:]
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    continue

                event_type = data.get("type", "")

                if event_type == "response.output_text.delta":
                    if not text_started:
                        yield StreamEvent(type=StreamEventType.TEXT_START)
                        text_started = True
                    yield StreamEvent(
                        type=StreamEventType.TEXT_DELTA,
                        delta=data.get("delta", ""),
                    )
                elif event_type == "response.function_call_arguments.delta":
                    yield StreamEvent(
                        type=StreamEventType.TOOL_CALL_DELTA,
                        delta=data.get("delta", ""),
                    )
                elif event_type == "response.output_item.done":
                    item = data.get("item", {})
                    if item.get("type") == "function_call":
                        args_str = item.get("arguments", "{}")
                        try:
                            args = json.loads(args_str) if isinstance(args_str, str) else args_str
                        except json.JSONDecodeError:
                            args = {}
                        yield StreamEvent(
                            type=StreamEventType.TOOL_CALL_END,
                            tool_call=ToolCall(
                                id=item.get("call_id", item.get("id", "")),
                                name=item.get("name", ""),
                                arguments=args,
                            ),
                        )
                    elif item.get("type") == "message":
                        if text_started:
                            yield StreamEvent(type=StreamEventType.TEXT_END)
                            text_started = False
                elif event_type == "response.completed":
                    resp_data = data.get("response", data)
                    accumulated_data = resp_data
                    if text_started:
                        yield StreamEvent(type=StreamEventType.TEXT_END)
                        text_started = False
                    response = self._parse_response(resp_data)
                    yield StreamEvent(
                        type=StreamEventType.FINISH,
                        finish_reason=response.finish_reason,
                        usage=response.usage,
                        response=response,
                    )

    # -- Error handling --

    def _raise_error(self, http_resp: httpx.Response) -> None:
        try:
            body = http_resp.json()
        except Exception:
            body = {"error": {"message": http_resp.text}}

        error_obj = body.get("error", {})
        message = error_obj.get("message", http_resp.text)
        error_code = error_obj.get("code") or error_obj.get("type")

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
        if status in (400, 422):
            classification = classify_error_message(message)
            if classification == "context_length":
                err_cls = ContextLengthError

        raise err_cls(
            message,
            provider="openai",
            error_code=error_code,
            raw=body,
            retry_after=retry_after,
        )
