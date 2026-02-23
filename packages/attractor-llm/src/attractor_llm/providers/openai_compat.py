"""OpenAI-compatible adapter using the Chat Completions API.

For third-party services (vLLM, Ollama, Together AI, Groq, etc.)
that implement the OpenAI Chat Completions protocol.
"""

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
    classify_error_message,
)
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
    "stop": "stop",
    "length": "length",
    "tool_calls": "tool_calls",
    "content_filter": "content_filter",
}


class OpenAICompatibleAdapter:
    """Adapter for OpenAI-compatible Chat Completions endpoints."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "http://localhost:8000",
        provider_name: str = "openai-compatible",
        http_client: httpx.AsyncClient | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._provider_name = provider_name
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = http_client or httpx.AsyncClient(
            headers=headers, timeout=httpx.Timeout(300.0)
        )

    @property
    def name(self) -> str:
        return self._provider_name

    async def complete(self, request: Request) -> Response:
        body = self._build_request_body(request, stream=False)
        http_resp = await self._client.post(
            f"{self._base_url}/v1/chat/completions", json=body
        )
        if http_resp.status_code >= 400:
            self._raise_error(http_resp)
        return self._parse_response(http_resp.json())

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        body = self._build_request_body(request, stream=True)
        async with self._client.stream(
            "POST", f"{self._base_url}/v1/chat/completions", json=body
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

        body["messages"] = [self._translate_message(m) for m in request.messages]

        if stream:
            body["stream"] = True

        if request.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in request.tools
            ]

        if request.tool_choice:
            tc = request.tool_choice
            if tc.mode in ("auto", "none", "required"):
                body["tool_choice"] = tc.mode
            elif tc.mode == "named":
                body["tool_choice"] = {
                    "type": "function",
                    "function": {"name": tc.tool_name},
                }

        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.top_p is not None:
            body["top_p"] = request.top_p
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.stop_sequences:
            body["stop"] = request.stop_sequences
        if request.response_format:
            if request.response_format.type == "json":
                body["response_format"] = {"type": "json_object"}
            elif request.response_format.type == "json_schema" and request.response_format.json_schema:
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "schema": request.response_format.json_schema,
                        "strict": request.response_format.strict,
                    },
                }

        return body

    def _translate_message(self, msg: Message) -> dict[str, Any]:
        if msg.role == Role.SYSTEM:
            return {"role": "system", "content": msg.text}
        if msg.role == Role.DEVELOPER:
            return {"role": "system", "content": msg.text}
        if msg.role == Role.USER:
            return {"role": "user", "content": msg.text}
        if msg.role == Role.TOOL:
            for p in msg.content:
                if p.kind == ContentKind.TOOL_RESULT and p.tool_result:
                    content = p.tool_result.content
                    if not isinstance(content, str):
                        content = json.dumps(content)
                    return {
                        "role": "tool",
                        "tool_call_id": p.tool_result.tool_call_id,
                        "content": content,
                    }
            return {"role": "tool", "content": ""}
        # ASSISTANT
        result: dict[str, Any] = {"role": "assistant"}
        text_parts = [p.text for p in msg.content if p.kind == ContentKind.TEXT and p.text]
        if text_parts:
            result["content"] = "".join(text_parts)
        tool_calls = []
        for p in msg.content:
            if p.kind == ContentKind.TOOL_CALL and p.tool_call:
                args = p.tool_call.arguments
                if isinstance(args, dict):
                    args = json.dumps(args)
                tool_calls.append({
                    "id": p.tool_call.id,
                    "type": "function",
                    "function": {
                        "name": p.tool_call.name,
                        "arguments": args,
                    },
                })
        if tool_calls:
            result["tool_calls"] = tool_calls
        return result

    # -- Response parsing --

    def _parse_response(self, data: dict[str, Any]) -> Response:
        content_parts: list[ContentPart] = []
        choices = data.get("choices", [])
        choice = choices[0] if choices else {}
        message = choice.get("message", {})

        if message.get("content"):
            content_parts.append(
                ContentPart(kind=ContentKind.TEXT, text=message["content"])
            )

        for tc in message.get("tool_calls", []):
            fn = tc.get("function", {})
            args_str = fn.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {}
            content_parts.append(
                ContentPart(
                    kind=ContentKind.TOOL_CALL,
                    tool_call=ToolCallData(
                        id=tc.get("id", ""),
                        name=fn.get("name", ""),
                        arguments=args,
                    ),
                )
            )

        msg = Message(role=Role.ASSISTANT, content=content_parts)

        raw_reason = choice.get("finish_reason", "stop")
        reason = _FINISH_MAP.get(raw_reason, "other") if raw_reason else "stop"

        usage_data = data.get("usage", {})
        usage = Usage(
            input_tokens=usage_data.get("prompt_tokens", 0),
            output_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
            raw=usage_data or None,
        )

        return Response(
            id=data.get("id", ""),
            model=data.get("model", ""),
            provider=self._provider_name,
            message=msg,
            finish_reason=FinishReason(reason=reason, raw=raw_reason),
            usage=usage,
            raw=data,
        )

    # -- Streaming --

    async def _parse_sse_stream(
        self, http_resp: httpx.Response
    ) -> AsyncIterator[StreamEvent]:
        text_started = False
        tool_calls_by_index: dict[int, dict[str, Any]] = {}

        async for line in http_resp.aiter_lines():
            if not line or line.startswith(":"):
                continue
            if line == "data: [DONE]":
                break
            if not line.startswith("data: "):
                continue

            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            choices = data.get("choices", [])
            if not choices:
                # Usage-only chunk
                usage_data = data.get("usage")
                if usage_data:
                    if text_started:
                        yield StreamEvent(type=StreamEventType.TEXT_END)
                        text_started = False
                    yield StreamEvent(
                        type=StreamEventType.FINISH,
                        usage=Usage(
                            input_tokens=usage_data.get("prompt_tokens", 0),
                            output_tokens=usage_data.get("completion_tokens", 0),
                            total_tokens=usage_data.get("total_tokens", 0),
                        ),
                    )
                continue

            choice = choices[0]
            delta = choice.get("delta", {})
            finish_reason = choice.get("finish_reason")

            # Text delta
            if delta.get("content"):
                if not text_started:
                    yield StreamEvent(type=StreamEventType.TEXT_START)
                    text_started = True
                yield StreamEvent(
                    type=StreamEventType.TEXT_DELTA,
                    delta=delta["content"],
                )

            # Tool call deltas
            for tc_delta in delta.get("tool_calls", []):
                idx = tc_delta.get("index", 0)
                if idx not in tool_calls_by_index:
                    tool_calls_by_index[idx] = {
                        "id": tc_delta.get("id", ""),
                        "name": tc_delta.get("function", {}).get("name", ""),
                        "arguments": "",
                    }
                    yield StreamEvent(
                        type=StreamEventType.TOOL_CALL_START,
                        tool_call=ToolCall(
                            id=tool_calls_by_index[idx]["id"],
                            name=tool_calls_by_index[idx]["name"],
                        ),
                    )
                args_chunk = tc_delta.get("function", {}).get("arguments", "")
                if args_chunk:
                    tool_calls_by_index[idx]["arguments"] += args_chunk
                    yield StreamEvent(
                        type=StreamEventType.TOOL_CALL_DELTA,
                        delta=args_chunk,
                    )

            if finish_reason:
                if text_started:
                    yield StreamEvent(type=StreamEventType.TEXT_END)
                    text_started = False
                for tc_data in tool_calls_by_index.values():
                    try:
                        args = json.loads(tc_data["arguments"]) if tc_data["arguments"] else {}
                    except json.JSONDecodeError:
                        args = {}
                    yield StreamEvent(
                        type=StreamEventType.TOOL_CALL_END,
                        tool_call=ToolCall(
                            id=tc_data["id"],
                            name=tc_data["name"],
                            arguments=args,
                        ),
                    )
                reason = _FINISH_MAP.get(finish_reason, "other")
                yield StreamEvent(
                    type=StreamEventType.FINISH,
                    finish_reason=FinishReason(reason=reason, raw=finish_reason),
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
        ra = http_resp.headers.get("retry-after")
        if ra:
            try:
                retry_after = float(ra)
            except ValueError:
                pass

        err_cls = _STATUS_MAP.get(http_resp.status_code, ServerError)
        raise err_cls(
            message,
            provider=self._provider_name,
            error_code=error_code,
            raw=body,
            retry_after=retry_after,
        )
