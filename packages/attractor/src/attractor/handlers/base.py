"""Handler interface and registry."""

from __future__ import annotations

from typing import Any, Protocol

from attractor.context import Context
from attractor.graph import Graph, Node, SHAPE_HANDLER_MAP
from attractor.outcome import Outcome


class Handler(Protocol):
    """Interface for node handlers."""

    async def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome: ...


class HandlerRegistry:
    """Maps handler type strings to handler instances."""

    def __init__(self, default_handler: Handler | None = None) -> None:
        self._handlers: dict[str, Handler] = {}
        self._default_handler = default_handler

    def register(self, type_string: str, handler: Handler) -> None:
        self._handlers[type_string] = handler

    def resolve(self, node: Node) -> Handler:
        # 1. Explicit type attribute
        if node.type and node.type in self._handlers:
            return self._handlers[node.type]
        # 2. Shape-based resolution
        handler_type = SHAPE_HANDLER_MAP.get(node.shape, "codergen")
        if handler_type in self._handlers:
            return self._handlers[handler_type]
        # 3. Default
        if self._default_handler is not None:
            return self._default_handler
        raise KeyError(f"No handler for node '{node.id}' (type='{node.type}', shape='{node.shape}')")

    @property
    def handlers(self) -> dict[str, Handler]:
        return dict(self._handlers)
