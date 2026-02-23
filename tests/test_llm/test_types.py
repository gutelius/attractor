"""Tests for attractor_llm.types."""

import pytest
from attractor_llm.types import (
    AudioData,
    ContentKind,
    ContentPart,
    DocumentData,
    FinishReason,
    ImageData,
    Message,
    RateLimitInfo,
    Request,
    Response,
    ResponseFormat,
    Role,
    StreamEvent,
    StreamEventType,
    ThinkingData,
    ToolCall,
    ToolCallData,
    ToolChoice,
    ToolResult,
    ToolResultData,
    Usage,
    Warning,
)


class TestRole:
    def test_values(self):
        assert Role.SYSTEM.value == "system"
        assert Role.USER.value == "user"
        assert Role.ASSISTANT.value == "assistant"
        assert Role.TOOL.value == "tool"
        assert Role.DEVELOPER.value == "developer"


class TestContentKind:
    def test_values(self):
        assert ContentKind.TEXT.value == "text"
        assert ContentKind.IMAGE.value == "image"
        assert ContentKind.AUDIO.value == "audio"
        assert ContentKind.DOCUMENT.value == "document"
        assert ContentKind.TOOL_CALL.value == "tool_call"
        assert ContentKind.TOOL_RESULT.value == "tool_result"
        assert ContentKind.THINKING.value == "thinking"
        assert ContentKind.REDACTED_THINKING.value == "redacted_thinking"


class TestMessage:
    def test_system_constructor(self):
        msg = Message.system("You are helpful.")
        assert msg.role == Role.SYSTEM
        assert len(msg.content) == 1
        assert msg.content[0].kind == ContentKind.TEXT
        assert msg.content[0].text == "You are helpful."

    def test_user_constructor(self):
        msg = Message.user("Hello")
        assert msg.role == Role.USER
        assert msg.text == "Hello"

    def test_assistant_constructor(self):
        msg = Message.assistant("Hi there")
        assert msg.role == Role.ASSISTANT
        assert msg.text == "Hi there"

    def test_tool_result_constructor(self):
        msg = Message.tool_result(tool_call_id="call_1", content="result", is_error=False)
        assert msg.role == Role.TOOL
        assert msg.content[0].kind == ContentKind.TOOL_RESULT
        assert msg.content[0].tool_result.tool_call_id == "call_1"
        assert msg.content[0].tool_result.content == "result"
        assert msg.content[0].tool_result.is_error is False

    def test_text_accessor(self):
        msg = Message(
            role=Role.ASSISTANT,
            content=[
                ContentPart(kind=ContentKind.TEXT, text="Hello "),
                ContentPart(kind=ContentKind.TEXT, text="world"),
            ],
        )
        assert msg.text == "Hello world"

    def test_text_accessor_no_text(self):
        msg = Message(role=Role.ASSISTANT, content=[])
        assert msg.text == ""

    def test_name_and_tool_call_id(self):
        msg = Message(role=Role.TOOL, content=[], name="my_tool", tool_call_id="call_1")
        assert msg.name == "my_tool"
        assert msg.tool_call_id == "call_1"


class TestContentPart:
    def test_text_part(self):
        p = ContentPart(kind=ContentKind.TEXT, text="hello")
        assert p.kind == ContentKind.TEXT
        assert p.text == "hello"

    def test_image_part(self):
        img = ImageData(url="https://example.com/img.png")
        p = ContentPart(kind=ContentKind.IMAGE, image=img)
        assert p.image.url == "https://example.com/img.png"

    def test_tool_call_part(self):
        tc = ToolCallData(id="call_1", name="get_weather", arguments={"city": "SF"})
        p = ContentPart(kind=ContentKind.TOOL_CALL, tool_call=tc)
        assert p.tool_call.name == "get_weather"

    def test_thinking_part(self):
        t = ThinkingData(text="Let me think...", signature="sig123", redacted=False)
        p = ContentPart(kind=ContentKind.THINKING, thinking=t)
        assert p.thinking.text == "Let me think..."
        assert p.thinking.signature == "sig123"

    def test_string_kind(self):
        """kind can be an arbitrary string for provider-specific content."""
        p = ContentPart(kind="custom_kind", text="data")
        assert p.kind == "custom_kind"


class TestRequest:
    def test_basic_construction(self):
        req = Request(
            model="gpt-5.2",
            messages=[Message.user("Hi")],
        )
        assert req.model == "gpt-5.2"
        assert len(req.messages) == 1
        assert req.provider is None
        assert req.tools is None

    def test_with_tools(self):
        req = Request(
            model="claude-opus-4-6",
            messages=[Message.user("Hi")],
            tool_choice=ToolChoice(mode="auto"),
        )
        assert req.tool_choice.mode == "auto"

    def test_provider_options(self):
        req = Request(
            model="claude-opus-4-6",
            messages=[],
            provider_options={"anthropic": {"thinking": {"type": "enabled"}}},
        )
        assert req.provider_options["anthropic"]["thinking"]["type"] == "enabled"


class TestResponse:
    def test_text_accessor(self):
        resp = Response(
            id="resp_1",
            model="gpt-5.2",
            provider="openai",
            message=Message.assistant("The answer is 42."),
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
        )
        assert resp.text == "The answer is 42."

    def test_tool_calls_accessor(self):
        tc = ToolCallData(id="call_1", name="get_weather", arguments={"city": "SF"})
        msg = Message(
            role=Role.ASSISTANT,
            content=[ContentPart(kind=ContentKind.TOOL_CALL, tool_call=tc)],
        )
        resp = Response(
            id="resp_1",
            model="gpt-5.2",
            provider="openai",
            message=msg,
            finish_reason=FinishReason(reason="tool_calls"),
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
        )
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "get_weather"

    def test_reasoning_accessor(self):
        msg = Message(
            role=Role.ASSISTANT,
            content=[
                ContentPart(
                    kind=ContentKind.THINKING,
                    thinking=ThinkingData(text="Reasoning here", redacted=False),
                ),
                ContentPart(kind=ContentKind.TEXT, text="Answer"),
            ],
        )
        resp = Response(
            id="resp_1",
            model="claude-opus-4-6",
            provider="anthropic",
            message=msg,
            finish_reason=FinishReason(reason="stop"),
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
        )
        assert resp.reasoning == "Reasoning here"
        assert resp.text == "Answer"


class TestUsage:
    def test_addition(self):
        a = Usage(input_tokens=10, output_tokens=5, total_tokens=15)
        b = Usage(input_tokens=20, output_tokens=10, total_tokens=30)
        result = a + b
        assert result.input_tokens == 30
        assert result.output_tokens == 15
        assert result.total_tokens == 45

    def test_addition_optional_fields(self):
        a = Usage(input_tokens=10, output_tokens=5, total_tokens=15, reasoning_tokens=100)
        b = Usage(input_tokens=20, output_tokens=10, total_tokens=30, reasoning_tokens=None)
        result = a + b
        assert result.reasoning_tokens == 100

    def test_addition_both_none(self):
        a = Usage(input_tokens=10, output_tokens=5, total_tokens=15)
        b = Usage(input_tokens=20, output_tokens=10, total_tokens=30)
        result = a + b
        assert result.reasoning_tokens is None

    def test_addition_cache_tokens(self):
        a = Usage(
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            cache_read_tokens=50,
            cache_write_tokens=20,
        )
        b = Usage(
            input_tokens=20,
            output_tokens=10,
            total_tokens=30,
            cache_read_tokens=30,
            cache_write_tokens=None,
        )
        result = a + b
        assert result.cache_read_tokens == 80
        assert result.cache_write_tokens == 20


class TestToolChoice:
    def test_auto(self):
        tc = ToolChoice(mode="auto")
        assert tc.mode == "auto"
        assert tc.tool_name is None

    def test_named(self):
        tc = ToolChoice(mode="named", tool_name="get_weather")
        assert tc.mode == "named"
        assert tc.tool_name == "get_weather"


class TestToolCall:
    def test_construction(self):
        tc = ToolCall(id="call_1", name="fn", arguments={"a": 1})
        assert tc.id == "call_1"
        assert tc.name == "fn"
        assert tc.arguments == {"a": 1}


class TestToolResult:
    def test_construction(self):
        tr = ToolResult(tool_call_id="call_1", content="result", is_error=False)
        assert tr.tool_call_id == "call_1"
        assert not tr.is_error


class TestFinishReason:
    def test_with_raw(self):
        fr = FinishReason(reason="stop", raw="end_turn")
        assert fr.reason == "stop"
        assert fr.raw == "end_turn"


class TestStreamEventType:
    def test_values(self):
        assert StreamEventType.TEXT_DELTA.value == "text_delta"
        assert StreamEventType.FINISH.value == "finish"
        assert StreamEventType.ERROR.value == "error"


class TestStreamEvent:
    def test_text_delta(self):
        evt = StreamEvent(type=StreamEventType.TEXT_DELTA, delta="hello")
        assert evt.type == StreamEventType.TEXT_DELTA
        assert evt.delta == "hello"


class TestResponseFormat:
    def test_json_schema(self):
        rf = ResponseFormat(type="json_schema", json_schema={"type": "object"}, strict=True)
        assert rf.type == "json_schema"
        assert rf.strict is True


class TestWarning:
    def test_construction(self):
        w = Warning(message="Deprecated model", code="deprecated")
        assert w.message == "Deprecated model"


class TestRateLimitInfo:
    def test_construction(self):
        rli = RateLimitInfo(requests_remaining=100, requests_limit=1000)
        assert rli.requests_remaining == 100


class TestImageData:
    def test_url(self):
        img = ImageData(url="https://example.com/img.png")
        assert img.url == "https://example.com/img.png"
        assert img.data is None

    def test_data(self):
        img = ImageData(data=b"\x89PNG", media_type="image/png")
        assert img.data == b"\x89PNG"


class TestDocumentData:
    def test_construction(self):
        doc = DocumentData(url="https://example.com/doc.pdf", media_type="application/pdf")
        assert doc.media_type == "application/pdf"
