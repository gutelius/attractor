"""Tests for handler registry and base handlers."""

import pytest

from attractor.context import Context
from attractor.graph import Graph, Node
from attractor.handlers.base import HandlerRegistry
from attractor.handlers.start_exit import StartHandler, ExitHandler
from attractor.handlers.conditional import ConditionalHandler
from attractor.outcome import StageStatus


class TestHandlerRegistry:
    def test_register_and_resolve_by_type(self):
        reg = HandlerRegistry()
        handler = StartHandler()
        reg.register("start", handler)
        node = Node(id="s", type="start")
        assert reg.resolve(node) is handler

    def test_resolve_by_shape(self):
        reg = HandlerRegistry()
        handler = StartHandler()
        reg.register("start", handler)
        node = Node(id="s", shape="Mdiamond")
        assert reg.resolve(node) is handler

    def test_explicit_type_overrides_shape(self):
        reg = HandlerRegistry()
        start = StartHandler()
        exit_ = ExitHandler()
        reg.register("start", start)
        reg.register("exit", exit_)
        # Node has Mdiamond shape (start) but explicit type=exit
        node = Node(id="x", shape="Mdiamond", type="exit")
        assert reg.resolve(node) is exit_

    def test_default_handler_fallback(self):
        default = ConditionalHandler()
        reg = HandlerRegistry(default_handler=default)
        node = Node(id="x", shape="box")  # no "codergen" registered
        assert reg.resolve(node) is default

    def test_no_handler_raises(self):
        reg = HandlerRegistry()
        node = Node(id="x", shape="box")
        with pytest.raises(KeyError, match="No handler"):
            reg.resolve(node)

    def test_register_replaces(self):
        reg = HandlerRegistry()
        h1 = StartHandler()
        h2 = StartHandler()
        reg.register("start", h1)
        reg.register("start", h2)
        node = Node(id="s", type="start")
        assert reg.resolve(node) is h2

    def test_handlers_property(self):
        reg = HandlerRegistry()
        reg.register("start", StartHandler())
        reg.register("exit", ExitHandler())
        assert set(reg.handlers.keys()) == {"start", "exit"}


class TestStartHandler:
    @pytest.mark.asyncio
    async def test_returns_success(self):
        handler = StartHandler()
        ctx = Context()
        g = Graph()
        node = Node(id="start", shape="Mdiamond")
        outcome = await handler.execute(node, ctx, g, "/tmp/logs")
        assert outcome.status == StageStatus.SUCCESS


class TestExitHandler:
    @pytest.mark.asyncio
    async def test_returns_success(self):
        handler = ExitHandler()
        ctx = Context()
        g = Graph()
        node = Node(id="exit", shape="Msquare")
        outcome = await handler.execute(node, ctx, g, "/tmp/logs")
        assert outcome.status == StageStatus.SUCCESS


class TestConditionalHandler:
    @pytest.mark.asyncio
    async def test_returns_success(self):
        handler = ConditionalHandler()
        ctx = Context()
        g = Graph()
        node = Node(id="cond", shape="diamond")
        outcome = await handler.execute(node, ctx, g, "/tmp/logs")
        assert outcome.status == StageStatus.SUCCESS
