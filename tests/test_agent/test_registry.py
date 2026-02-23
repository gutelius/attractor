"""Tests for tool registry."""

import pytest

from attractor_llm.types import ToolDefinition, ToolResult
from attractor_agent.tools.registry import ToolRegistry


def make_tool_def(name: str, desc: str = "test") -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=desc,
        parameters={"type": "object", "properties": {}},
    )


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        defn = make_tool_def("my_tool")
        reg.register(defn, lambda: "ok")
        assert reg.get("my_tool") is not None
        assert reg.get("my_tool").definition.name == "my_tool"

    def test_unregister(self):
        reg = ToolRegistry()
        reg.register(make_tool_def("t"), lambda: None)
        assert reg.unregister("t")
        assert reg.get("t") is None
        assert not reg.unregister("t")  # already removed

    def test_definitions(self):
        reg = ToolRegistry()
        reg.register(make_tool_def("a"), lambda: None)
        reg.register(make_tool_def("b"), lambda: None)
        defs = reg.definitions()
        assert len(defs) == 2
        names = {d.name for d in defs}
        assert names == {"a", "b"}

    def test_name_collision_latest_wins(self):
        reg = ToolRegistry()
        reg.register(make_tool_def("x", "first"), lambda: "first")
        reg.register(make_tool_def("x", "second"), lambda: "second")
        assert reg.get("x").definition.description == "second"
        assert len(reg) == 1

    async def test_execute_sync(self):
        reg = ToolRegistry()
        reg.register(make_tool_def("add"), lambda a, b: a + b)
        result = await reg.execute("add", {"a": 1, "b": 2})
        assert result.content == "3"
        assert not result.is_error

    async def test_execute_async(self):
        reg = ToolRegistry()

        async def async_tool(x: str) -> str:
            return f"got {x}"

        reg.register(make_tool_def("atool"), async_tool)
        result = await reg.execute("atool", {"x": "hello"})
        assert result.content == "got hello"

    async def test_execute_unknown(self):
        reg = ToolRegistry()
        result = await reg.execute("nope", {})
        assert result.is_error
        assert "Unknown tool" in str(result.content)

    async def test_execute_error(self):
        reg = ToolRegistry()
        reg.register(make_tool_def("bad"), lambda: 1 / 0)
        result = await reg.execute("bad", {})
        assert result.is_error
        assert "Tool error" in str(result.content)

    def test_contains(self):
        reg = ToolRegistry()
        reg.register(make_tool_def("x"), lambda: None)
        assert "x" in reg
        assert "y" not in reg

    def test_names(self):
        reg = ToolRegistry()
        reg.register(make_tool_def("a"), lambda: None)
        reg.register(make_tool_def("b"), lambda: None)
        assert set(reg.names()) == {"a", "b"}
