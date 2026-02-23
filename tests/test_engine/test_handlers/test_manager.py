"""Tests for ManagerLoopHandler."""

import pytest

from attractor.context import Context
from attractor.graph import Graph, Node
from attractor.handlers.manager import ManagerLoopHandler
from attractor.outcome import StageStatus


class TestManagerLoopHandler:
    @pytest.mark.asyncio
    async def test_child_completes_success(self):
        handler = ManagerLoopHandler()
        node = Node(id="mgr", shape="house")
        node.extra["manager.poll_interval"] = "0.01s"
        node.extra["manager.max_cycles"] = "5"
        ctx = Context()
        ctx.set("stack.child.status", "completed")
        ctx.set("stack.child.outcome", "success")

        outcome = await handler.execute(node, ctx, Graph(), "/tmp")
        assert outcome.status == StageStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_child_fails(self):
        handler = ManagerLoopHandler()
        node = Node(id="mgr", shape="house")
        node.extra["manager.poll_interval"] = "0.01s"
        node.extra["manager.max_cycles"] = "5"
        ctx = Context()
        ctx.set("stack.child.status", "failed")

        outcome = await handler.execute(node, ctx, Graph(), "/tmp")
        assert outcome.status == StageStatus.FAIL

    @pytest.mark.asyncio
    async def test_stop_condition(self):
        handler = ManagerLoopHandler()
        node = Node(id="mgr", shape="house")
        node.extra["manager.poll_interval"] = "0.01s"
        node.extra["manager.max_cycles"] = "5"
        node.extra["manager.stop_condition"] = "done=true"
        ctx = Context()
        ctx.set("done", "true")

        outcome = await handler.execute(node, ctx, Graph(), "/tmp")
        assert outcome.status == StageStatus.SUCCESS
        assert "Stop condition" in outcome.notes

    @pytest.mark.asyncio
    async def test_max_cycles_exceeded(self):
        handler = ManagerLoopHandler()
        node = Node(id="mgr", shape="house")
        node.extra["manager.poll_interval"] = "0.001s"
        node.extra["manager.max_cycles"] = "3"
        ctx = Context()

        outcome = await handler.execute(node, ctx, Graph(), "/tmp")
        assert outcome.status == StageStatus.FAIL
        assert "Max cycles" in outcome.failure_reason

    @pytest.mark.asyncio
    async def test_with_child_executor(self):
        started = []

        async def executor(dotfile, ctx):
            started.append(dotfile)
            ctx.set("stack.child.status", "completed")
            ctx.set("stack.child.outcome", "success")

        handler = ManagerLoopHandler(child_executor=executor)
        node = Node(id="mgr", shape="house")
        node.extra["manager.poll_interval"] = "0.01s"
        node.extra["manager.max_cycles"] = "5"
        node.extra["stack.child_dotfile"] = "child.dot"
        ctx = Context()

        outcome = await handler.execute(node, ctx, Graph(), "/tmp")
        assert outcome.status == StageStatus.SUCCESS
        assert "child.dot" in started
