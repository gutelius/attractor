"""Core type definitions for the unified LLM client."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    DEVELOPER = "developer"


class ContentKind(Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    DOCUMENT = "document"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    THINKING = "thinking"
    REDACTED_THINKING = "redacted_thinking"


class StreamEventType(Enum):
    STREAM_START = "stream_start"
    TEXT_START = "text_start"
    TEXT_DELTA = "text_delta"
    TEXT_END = "text_end"
    REASONING_START = "reasoning_start"
    REASONING_DELTA = "reasoning_delta"
    REASONING_END = "reasoning_end"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_END = "tool_call_end"
    FINISH = "finish"
    ERROR = "error"
    PROVIDER_EVENT = "provider_event"


@dataclass
class ImageData:
    url: str | None = None
    data: bytes | None = None
    media_type: str | None = None
    detail: str | None = None


@dataclass
class AudioData:
    url: str | None = None
    data: bytes | None = None
    media_type: str | None = None


@dataclass
class DocumentData:
    url: str | None = None
    data: bytes | None = None
    media_type: str | None = None
    file_name: str | None = None


@dataclass
class ToolCallData:
    id: str = ""
    name: str = ""
    arguments: dict[str, Any] | str = field(default_factory=dict)
    type: str = "function"


@dataclass
class ToolResultData:
    tool_call_id: str = ""
    content: str | dict[str, Any] = ""
    is_error: bool = False
    image_data: bytes | None = None
    image_media_type: str | None = None


@dataclass
class ThinkingData:
    text: str = ""
    signature: str | None = None
    redacted: bool = False


@dataclass
class ContentPart:
    kind: ContentKind | str = ContentKind.TEXT
    text: str | None = None
    image: ImageData | None = None
    audio: AudioData | None = None
    document: DocumentData | None = None
    tool_call: ToolCallData | None = None
    tool_result: ToolResultData | None = None
    thinking: ThinkingData | None = None


@dataclass
class Message:
    role: Role = Role.USER
    content: list[ContentPart] = field(default_factory=list)
    name: str | None = None
    tool_call_id: str | None = None

    @property
    def text(self) -> str:
        return "".join(
            p.text for p in self.content if p.kind == ContentKind.TEXT and p.text
        )

    @classmethod
    def system(cls, text: str) -> Message:
        return cls(
            role=Role.SYSTEM,
            content=[ContentPart(kind=ContentKind.TEXT, text=text)],
        )

    @classmethod
    def user(cls, text: str) -> Message:
        return cls(
            role=Role.USER,
            content=[ContentPart(kind=ContentKind.TEXT, text=text)],
        )

    @classmethod
    def assistant(cls, text: str) -> Message:
        return cls(
            role=Role.ASSISTANT,
            content=[ContentPart(kind=ContentKind.TEXT, text=text)],
        )

    @classmethod
    def tool_result(
        cls,
        tool_call_id: str,
        content: str | dict[str, Any] = "",
        is_error: bool = False,
    ) -> Message:
        return cls(
            role=Role.TOOL,
            content=[
                ContentPart(
                    kind=ContentKind.TOOL_RESULT,
                    tool_result=ToolResultData(
                        tool_call_id=tool_call_id,
                        content=content,
                        is_error=is_error,
                    ),
                )
            ],
            tool_call_id=tool_call_id,
        )


@dataclass
class ToolChoice:
    mode: str = "auto"
    tool_name: str | None = None


@dataclass
class ResponseFormat:
    type: str = "text"
    json_schema: dict[str, Any] | None = None
    strict: bool = False


@dataclass
class Request:
    model: str = ""
    messages: list[Message] = field(default_factory=list)
    provider: str | None = None
    tools: list[ToolDefinition] | None = None
    tool_choice: ToolChoice | None = None
    response_format: ResponseFormat | None = None
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop_sequences: list[str] | None = None
    reasoning_effort: str | None = None
    metadata: dict[str, str] | None = None
    provider_options: dict[str, Any] | None = None


@dataclass
class FinishReason:
    reason: str = "stop"
    raw: str | None = None


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int | None = None
    cache_read_tokens: int | None = None
    cache_write_tokens: int | None = None
    raw: dict[str, Any] | None = None

    def __add__(self, other: Usage) -> Usage:
        def _add_optional(a: int | None, b: int | None) -> int | None:
            if a is None and b is None:
                return None
            return (a or 0) + (b or 0)

        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            reasoning_tokens=_add_optional(self.reasoning_tokens, other.reasoning_tokens),
            cache_read_tokens=_add_optional(self.cache_read_tokens, other.cache_read_tokens),
            cache_write_tokens=_add_optional(self.cache_write_tokens, other.cache_write_tokens),
        )


@dataclass
class Warning:
    message: str = ""
    code: str | None = None


@dataclass
class RateLimitInfo:
    requests_remaining: int | None = None
    requests_limit: int | None = None
    tokens_remaining: int | None = None
    tokens_limit: int | None = None
    reset_at: str | None = None


@dataclass
class ToolCall:
    id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: str | None = None


@dataclass
class ToolResult:
    tool_call_id: str = ""
    content: str | dict[str, Any] | list[Any] = ""
    is_error: bool = False


@dataclass
class ToolDefinition:
    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    execute: Any = None


@dataclass
class Response:
    id: str = ""
    model: str = ""
    provider: str = ""
    message: Message = field(default_factory=Message)
    finish_reason: FinishReason = field(default_factory=FinishReason)
    usage: Usage = field(default_factory=Usage)
    raw: dict[str, Any] | None = None
    warnings: list[Warning] = field(default_factory=list)
    rate_limit: RateLimitInfo | None = None

    @property
    def text(self) -> str:
        return self.message.text

    @property
    def tool_calls(self) -> list[ToolCall]:
        calls = []
        for p in self.message.content:
            if p.kind == ContentKind.TOOL_CALL and p.tool_call:
                calls.append(
                    ToolCall(
                        id=p.tool_call.id,
                        name=p.tool_call.name,
                        arguments=p.tool_call.arguments
                        if isinstance(p.tool_call.arguments, dict)
                        else {},
                        raw_arguments=p.tool_call.arguments
                        if isinstance(p.tool_call.arguments, str)
                        else None,
                    )
                )
        return calls

    @property
    def reasoning(self) -> str | None:
        parts = [
            p.thinking.text
            for p in self.message.content
            if p.kind == ContentKind.THINKING and p.thinking and p.thinking.text
        ]
        return "".join(parts) if parts else None


@dataclass
class StreamEvent:
    type: StreamEventType | str = StreamEventType.TEXT_DELTA
    delta: str | None = None
    text_id: str | None = None
    reasoning_delta: str | None = None
    tool_call: ToolCall | None = None
    finish_reason: FinishReason | None = None
    usage: Usage | None = None
    response: Response | None = None
    error: Any | None = None
    raw: dict[str, Any] | None = None
