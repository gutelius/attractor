"""Tool registry for managing available tools."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from attractor_llm.types import ToolDefinition, ToolResult


@dataclass
class RegisteredTool:
    """A tool registered in the registry."""

    definition: ToolDefinition
    executor: Callable[..., Any]


class ToolRegistry:
    """Registry for tool definitions and executors."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(
        self,
        definition: ToolDefinition,
        executor: Callable[..., Any],
    ) -> None:
        """Register a tool. Latest registration wins on name collision."""
        self._tools[definition.name] = RegisteredTool(
            definition=definition, executor=executor
        )

    def unregister(self, name: str) -> bool:
        """Remove a tool. Returns True if it existed."""
        return self._tools.pop(name, None) is not None

    def get(self, name: str) -> RegisteredTool | None:
        """Get a registered tool by name."""
        return self._tools.get(name)

    def definitions(self) -> list[ToolDefinition]:
        """Return all tool definitions (for LLM requests)."""
        return [t.definition for t in self._tools.values()]

    def names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool by name with the given arguments."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                tool_call_id="",
                content=f"Unknown tool: {name}",
                is_error=True,
            )
        try:
            if inspect.iscoroutinefunction(tool.executor):
                result = await tool.executor(**arguments)
            else:
                result = tool.executor(**arguments)
            content = result if isinstance(result, (str, dict, list)) else str(result)
            return ToolResult(tool_call_id="", content=content, is_error=False)
        except Exception as e:
            return ToolResult(
                tool_call_id="", content=f"Tool error: {e}", is_error=True
            )

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
