"""Conditional handler — routing is handled by the engine, not the handler."""

from __future__ import annotations

from attractor.context import Context
from attractor.graph import Graph, Node
from attractor.outcome import Outcome, StageStatus


class ConditionalHandler:
    """No-op handler for diamond/conditional nodes.

    The actual routing logic is in the engine's edge selection algorithm.
    This handler simply returns SUCCESS so the engine proceeds to edge selection.
    """

    async def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        return Outcome(status=StageStatus.SUCCESS)
