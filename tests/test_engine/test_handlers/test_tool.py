"""Tests for ToolHandler."""

import pytest

from attractor.context import Context
from attractor.graph import Graph, Node
from attractor.handlers.tool import ToolHandler
from attractor.outcome import StageStatus


class TestToolHandler:
    @pytest.mark.asyncio
    async def test_successful_command(self, tmp_path):
        handler = ToolHandler()
        node = Node(id="tool1", shape="parallelogram")
        node.extra["tool_command"] = "echo hello"
        ctx = Context()
        outcome = await handler.execute(node, ctx, Graph(), str(tmp_path))

        assert outcome.status == StageStatus.SUCCESS
        assert "hello" in outcome.context_updates["tool.output"]

    @pytest.mark.asyncio
    async def test_no_command_fails(self):
        handler = ToolHandler()
        node = Node(id="t", shape="parallelogram")
        outcome = await handler.execute(node, Context(), Graph(), "/tmp")

        assert outcome.status == StageStatus.FAIL
        assert "No tool_command" in outcome.failure_reason

    @pytest.mark.asyncio
    async def test_failing_command(self, tmp_path):
        handler = ToolHandler()
        node = Node(id="t", shape="parallelogram")
        node.extra["tool_command"] = "exit 1"
        outcome = await handler.execute(node, Context(), Graph(), str(tmp_path))

        assert outcome.status == StageStatus.FAIL
        assert "code 1" in outcome.failure_reason

    @pytest.mark.asyncio
    async def test_timeout(self, tmp_path):
        handler = ToolHandler()
        node = Node(id="t", shape="parallelogram", timeout="0.1s")
        node.extra["tool_command"] = "sleep 10"
        outcome = await handler.execute(node, Context(), Graph(), str(tmp_path))

        assert outcome.status == StageStatus.FAIL
        assert "timed out" in outcome.failure_reason

    @pytest.mark.asyncio
    async def test_writes_output_log(self, tmp_path):
        handler = ToolHandler()
        node = Node(id="t")
        node.extra["tool_command"] = "echo test_output"
        await handler.execute(node, Context(), Graph(), str(tmp_path))

        output_file = tmp_path / "t" / "tool_output.txt"
        assert output_file.exists()
        assert "test_output" in output_file.read_text()
