"""Start and Exit handlers."""

from __future__ import annotations

from attractor.context import Context
from attractor.graph import Graph, Node
from attractor.outcome import Outcome, StageStatus


class StartHandler:
    """No-op handler for pipeline entry point."""

    async def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        return Outcome(status=StageStatus.SUCCESS)


class ExitHandler:
    """No-op handler for pipeline exit point."""

    async def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        return Outcome(status=StageStatus.SUCCESS)
