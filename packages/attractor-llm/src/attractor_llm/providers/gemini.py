"""Gemini provider adapter using the generateContent API."""

from __future__ import annotations

import json
import uuid
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
    ThinkingData,
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
    429: RateLimitError,
    500: ServerError,
    502: ServerError,
    503: ServerError,
    504: ServerError,
}

_FINISH_MAP: dict[str, str] = {
    "STOP": "stop",
    "MAX_TOKENS": "length",
    "SAFETY": "content_filter",
    "RECITATION": "content_filter",
}


class GeminiAdapter:
    """Adapter for the Gemini generateContent API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://generativelanguage.googleapis.com",
        http_client: httpx.AsyncClient | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._client = http_client or httpx.AsyncClient(
            headers={"Content-Type": "application/json"},
            timeout=httpx.Timeout(300.0),
        )
        # Map synthetic call IDs -> function names for tool result routing
        self._call_id_to_name: dict[str, str] = {}

    @property
    def name(self) -> str:
        return "gemini"

    async def complete(self, request: Request) -> Response:
        body = self._build_request_body(request)
        url = f"{self._base_url}/v1beta/models/{request.model}:generateContent?key={self._api_key}"
        http_resp = await self._client.post(url, json=body)
        if http_resp.status_code >= 400:
            self._raise_error(http_resp)
        return self._parse_response(http_resp.json())

    async def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        body = self._build_request_body(request)
        url = f"{self._base_url}/v1beta/models/{request.model}:streamGenerateContent?alt=sse&key={self._api_key}"
        async with self._client.stream("POST", url, json=body) as http_resp:
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

    def _build_request_body(self, request: Request) -> dict[str, Any]:
        body: dict[str, Any] = {}

        system_parts, contents = self._translate_messages(request.messages)
        if system_parts:
            body["systemInstruction"] = {"parts": system_parts}
        body["contents"] = contents

        config: dict[str, Any] = {}
        if request.temperature is not None:
            config["temperature"] = request.temperature
        if request.top_p is not None:
            config["topP"] = request.top_p
        if request.max_tokens is not None:
            config["maxOutputTokens"] = request.max_tokens
        if request.stop_sequences:
            config["stopSequences"] = request.stop_sequences
        if request.response_format:
            if request.response_format.type == "json":
                config["responseMimeType"] = "application/json"
            elif request.response_format.type == "json_schema" and request.response_format.json_schema:
                config["responseMimeType"] = "application/json"
                config["responseSchema"] = request.response_format.json_schema
        if config:
            body["generationConfig"] = config

        if request.tools:
            body["tools"] = [{"functionDeclarations": [
                self._translate_tool(t) for t in request.tools
            ]}]

        if request.tool_choice:
            tc = self._translate_tool_choice(request.tool_choice)
            if tc:
                body["toolConfig"] = {"functionCallingConfig": tc}

        # Provider options
        opts = (request.provider_options or {}).get("gemini", {})
        for k, v in opts.items():
            body[k] = v

        return body

    def _translate_messages(
        self, messages: list[Message]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        system_parts: list[dict[str, Any]] = []
        contents: list[dict[str, Any]] = []

        for msg in messages:
            if msg.role in (Role.SYSTEM, Role.DEVELOPER):
                for p in msg.content:
                    if p.text:
                        system_parts.append({"text": p.text})
                continue

            if msg.role == Role.TOOL:
                parts: list[dict[str, Any]] = []
                for p in msg.content:
                    if p.kind == ContentKind.TOOL_RESULT and p.tool_result:
                        # Use function name (not ID) for Gemini
                        fn_name = self._call_id_to_name.get(
                            p.tool_result.tool_call_id,
                            p.tool_result.tool_call_id,
                        )
                        content = p.tool_result.content
                        if isinstance(content, str):
                            content = {"result": content}
                        parts.append({
                            "functionResponse": {
                                "name": fn_name,
                                "response": content,
                            }
                        })
                if parts:
                    contents.append({"role": "user", "parts": parts})
                continue

            role = "user" if msg.role == Role.USER else "model"
            parts = []

            for p in msg.content:
                if p.kind == ContentKind.TEXT and p.text is not None:
                    parts.append({"text": p.text})
                elif p.kind == ContentKind.TOOL_CALL and p.tool_call:
                    args = p.tool_call.arguments
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    parts.append({
                        "functionCall": {
                            "name": p.tool_call.name,
                            "args": args,
                        }
                    })
                    # Track synthetic ID -> name mapping
                    if p.tool_call.id:
                        self._call_id_to_name[p.tool_call.id] = p.tool_call.name
                elif p.kind == ContentKind.IMAGE and p.image:
                    if p.image.url:
                        parts.append({
                            "fileData": {
                                "mimeType": p.image.media_type or "image/png",
                                "fileUri": p.image.url,
                            }
                        })
                    elif p.image.data:
                        import base64
                        parts.append({
                            "inlineData": {
                                "mimeType": p.image.media_type or "image/png",
                                "data": base64.b64encode(p.image.data).decode(),
                            }
                        })

            if parts:
                contents.append({"role": role, "parts": parts})

        return system_parts, contents

    def _translate_tool(self, tool: Any) -> dict[str, Any]:
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        }

    def _translate_tool_choice(self, tc: Any) -> dict[str, Any] | None:
        if tc.mode == "auto":
            return {"mode": "AUTO"}
        if tc.mode == "none":
            return {"mode": "NONE"}
        if tc.mode == "required":
            return {"mode": "ANY"}
        if tc.mode == "named":
            return {"mode": "ANY", "allowedFunctionNames": [tc.tool_name]}
        return None

    # -- Response parsing --

    def _parse_response(self, data: dict[str, Any]) -> Response:
        content_parts: list[ContentPart] = []
        has_tool_calls = False

        candidates = data.get("candidates", [])
        candidate = candidates[0] if candidates else {}
        parts = candidate.get("content", {}).get("parts", [])

        for part in parts:
            if "text" in part:
                content_parts.append(
                    ContentPart(kind=ContentKind.TEXT, text=part["text"])
                )
            elif "functionCall" in part:
                has_tool_calls = True
                fc = part["functionCall"]
                call_id = f"call_{uuid.uuid4().hex[:12]}"
                self._call_id_to_name[call_id] = fc.get("name", "")
                content_parts.append(
                    ContentPart(
                        kind=ContentKind.TOOL_CALL,
                        tool_call=ToolCallData(
                            id=call_id,
                            name=fc.get("name", ""),
                            arguments=fc.get("args", {}),
                        ),
                    )
                )
            elif "thought" in part:
                content_parts.append(
                    ContentPart(
                        kind=ContentKind.THINKING,
                        thinking=ThinkingData(text=part["thought"], redacted=False),
                    )
                )

        msg = Message(role=Role.ASSISTANT, content=content_parts)

        # Finish reason
        raw_reason = candidate.get("finishReason", "STOP")
        if has_tool_calls:
            reason = "tool_calls"
        else:
            reason = _FINISH_MAP.get(raw_reason, "other")
        fr = FinishReason(reason=reason, raw=raw_reason)

        # Usage
        usage_meta = data.get("usageMetadata", {})
        usage = Usage(
            input_tokens=usage_meta.get("promptTokenCount", 0),
            output_tokens=usage_meta.get("candidatesTokenCount", 0),
            total_tokens=usage_meta.get("totalTokenCount", 0),
            reasoning_tokens=usage_meta.get("thoughtsTokenCount"),
            cache_read_tokens=usage_meta.get("cachedContentTokenCount"),
            raw=usage_meta or None,
        )

        return Response(
            id=data.get("id", ""),
            model=data.get("modelVersion", ""),
            provider="gemini",
            message=msg,
            finish_reason=fr,
            usage=usage,
            raw=data,
        )

    # -- Streaming --

    async def _parse_sse_stream(
        self, http_resp: httpx.Response
    ) -> AsyncIterator[StreamEvent]:
        text_started = False
        last_usage: Usage | None = None

        async for line in http_resp.aiter_lines():
            if not line or line.startswith(":"):
                continue
            if not line.startswith("data: "):
                continue

            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            candidates = data.get("candidates", [])
            candidate = candidates[0] if candidates else {}
            parts = candidate.get("content", {}).get("parts", [])

            for part in parts:
                if "text" in part:
                    if not text_started:
                        yield StreamEvent(type=StreamEventType.TEXT_START)
                        text_started = True
                    yield StreamEvent(
                        type=StreamEventType.TEXT_DELTA,
                        delta=part["text"],
                    )
                elif "functionCall" in part:
                    fc = part["functionCall"]
                    call_id = f"call_{uuid.uuid4().hex[:12]}"
                    self._call_id_to_name[call_id] = fc.get("name", "")
                    tc = ToolCall(
                        id=call_id,
                        name=fc.get("name", ""),
                        arguments=fc.get("args", {}),
                    )
                    yield StreamEvent(type=StreamEventType.TOOL_CALL_START, tool_call=tc)
                    yield StreamEvent(type=StreamEventType.TOOL_CALL_END, tool_call=tc)

            # Check for usage
            usage_meta = data.get("usageMetadata", {})
            if usage_meta:
                last_usage = Usage(
                    input_tokens=usage_meta.get("promptTokenCount", 0),
                    output_tokens=usage_meta.get("candidatesTokenCount", 0),
                    total_tokens=usage_meta.get("totalTokenCount", 0),
                    reasoning_tokens=usage_meta.get("thoughtsTokenCount"),
                )

            # Check finish
            finish_reason = candidate.get("finishReason")
            if finish_reason:
                if text_started:
                    yield StreamEvent(type=StreamEventType.TEXT_END)
                    text_started = False
                reason = _FINISH_MAP.get(finish_reason, "other")
                yield StreamEvent(
                    type=StreamEventType.FINISH,
                    finish_reason=FinishReason(reason=reason, raw=finish_reason),
                    usage=last_usage,
                )

    # -- Error handling --

    def _raise_error(self, http_resp: httpx.Response) -> None:
        try:
            body = http_resp.json()
        except Exception:
            body = {"error": {"message": http_resp.text}}

        error_obj = body.get("error", {})
        message = error_obj.get("message", http_resp.text)
        error_code = error_obj.get("status") or error_obj.get("code")

        status = http_resp.status_code
        err_cls = _STATUS_MAP.get(status, ServerError)

        raise err_cls(
            message,
            provider="gemini",
            error_code=str(error_code) if error_code else None,
            raw=body,
        )
