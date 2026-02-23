"""High-level generate() API with tool execution loop."""

from __future__ import annotations

import asyncio
import inspect
import json
from dataclasses import dataclass, field
from typing import Any

from attractor_llm.errors import ConfigurationError, SDKError
from attractor_llm.retry import RetryPolicy, retry
from attractor_llm.types import (
    ContentKind,
    ContentPart,
    FinishReason,
    Message,
    Request,
    Response,
    Role,
    ToolCall,
    ToolChoice,
    ToolDefinition,
    ToolResult,
    ToolResultData,
    Usage,
    Warning,
)


@dataclass
class StepResult:
    text: str = ""
    reasoning: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    finish_reason: FinishReason = field(default_factory=FinishReason)
    usage: Usage = field(default_factory=Usage)
    response: Response = field(default_factory=Response)
    warnings: list[Warning] = field(default_factory=list)


@dataclass
class GenerateResult:
    text: str = ""
    reasoning: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    finish_reason: FinishReason = field(default_factory=FinishReason)
    usage: Usage = field(default_factory=Usage)
    total_usage: Usage = field(default_factory=Usage)
    steps: list[StepResult] = field(default_factory=list)
    response: Response = field(default_factory=Response)
    output: Any = None


async def generate(
    model: str,
    prompt: str | None = None,
    messages: list[Message] | None = None,
    system: str | None = None,
    tools: list[ToolDefinition] | None = None,
    tool_choice: ToolChoice | None = None,
    max_tool_rounds: int = 1,
    response_format: Any = None,
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    stop_sequences: list[str] | None = None,
    reasoning_effort: str | None = None,
    provider: str | None = None,
    provider_options: dict[str, Any] | None = None,
    max_retries: int = 2,
    client: Any = None,
) -> GenerateResult:
    """High-level generation with automatic tool execution loop."""
    if prompt is not None and messages is not None:
        raise ConfigurationError("Cannot specify both 'prompt' and 'messages'")

    # Build initial messages
    conversation: list[Message] = []
    if system:
        conversation.append(Message.system(system))
    if messages:
        conversation.extend(messages)
    elif prompt is not None:
        conversation.append(Message.user(prompt))

    # Resolve client
    if client is None:
        from attractor_llm.client import get_default_client
        client = get_default_client()

    # Build tool definitions (without execute handlers) for the request
    tool_defs = tools
    tool_map: dict[str, Any] = {}
    if tools:
        for t in tools:
            if t.execute is not None:
                tool_map[t.name] = t.execute

    policy = RetryPolicy(max_retries=max_retries, base_delay=0.5)
    steps: list[StepResult] = []
    total_usage = Usage()

    for round_idx in range(max_tool_rounds + 1):
        request = Request(
            model=model,
            messages=list(conversation),
            provider=provider,
            tools=tool_defs,
            tool_choice=tool_choice,
            response_format=response_format,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            stop_sequences=stop_sequences,
            reasoning_effort=reasoning_effort,
            provider_options=provider_options,
        )

        # Retry-wrapped LLM call
        resp = await retry(lambda: client.complete(request), policy)

        step = StepResult(
            text=resp.text,
            reasoning=resp.reasoning,
            tool_calls=resp.tool_calls,
            finish_reason=resp.finish_reason,
            usage=resp.usage,
            response=resp,
            warnings=resp.warnings,
        )

        total_usage = total_usage + resp.usage

        # If there are tool calls and we have active tools, execute them
        if resp.tool_calls and tool_map and round_idx < max_tool_rounds:
            # Append assistant message with tool calls to conversation
            conversation.append(resp.message)

            # Execute tools concurrently
            tool_results = await _execute_tools(resp.tool_calls, tool_map)
            step.tool_results = tool_results

            # Append tool results to conversation
            for tr in tool_results:
                conversation.append(
                    Message.tool_result(
                        tool_call_id=tr.tool_call_id,
                        content=tr.content,
                        is_error=tr.is_error,
                    )
                )

            steps.append(step)
            continue

        # No tool calls or max rounds reached — done
        steps.append(step)
        break

    final_step = steps[-1]
    return GenerateResult(
        text=final_step.text,
        reasoning=final_step.reasoning,
        tool_calls=final_step.tool_calls,
        tool_results=final_step.tool_results,
        finish_reason=final_step.finish_reason,
        usage=final_step.usage,
        total_usage=total_usage,
        steps=steps,
        response=final_step.response,
    )


async def _execute_tools(
    tool_calls: list[ToolCall],
    tool_map: dict[str, Any],
) -> list[ToolResult]:
    """Execute tool calls concurrently."""

    async def _run_one(tc: ToolCall) -> ToolResult:
        handler = tool_map.get(tc.name)
        if handler is None:
            return ToolResult(
                tool_call_id=tc.id,
                content=f"Unknown tool: {tc.name}",
                is_error=True,
            )
        try:
            if inspect.iscoroutinefunction(handler):
                result = await handler(**tc.arguments)
            else:
                result = handler(**tc.arguments)
            content = result if isinstance(result, (str, dict, list)) else str(result)
            return ToolResult(tool_call_id=tc.id, content=content, is_error=False)
        except Exception as e:
            return ToolResult(
                tool_call_id=tc.id,
                content=f"Tool error: {e}",
                is_error=True,
            )

    results = await asyncio.gather(*[_run_one(tc) for tc in tool_calls])
    return list(results)
