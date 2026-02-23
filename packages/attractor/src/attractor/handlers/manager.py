"""Manager loop handler — supervises a child pipeline."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from attractor.conditions import evaluate_condition
from attractor.context import Context
from attractor.graph import Graph, Node
from attractor.outcome import Outcome, StageStatus


class ManagerLoopHandler:
    """Orchestrates sprint-based iteration by supervising a child pipeline."""

    def __init__(self, child_executor: Any = None) -> None:
        self.child_executor = child_executor

    async def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        poll_interval = _parse_duration(node.extra.get("manager.poll_interval", "0.1s"))
        max_cycles = int(node.extra.get("manager.max_cycles", 1000))
        stop_condition = node.extra.get("manager.stop_condition", "")
        actions = [a.strip() for a in node.extra.get("manager.actions", "observe,wait").split(",")]

        # 1. Auto-start child if configured
        if node.extra.get("stack.child_autostart", "true") == "true" and self.child_executor:
            child_dotfile = node.extra.get("stack.child_dotfile", "")
            if child_dotfile:
                await self.child_executor(child_dotfile, context)

        # 2. Observation loop
        for cycle in range(1, max_cycles + 1):
            # Check child status from context
            child_status = context.get_string("stack.child.status")
            if child_status in ("completed", "failed"):
                child_outcome = context.get_string("stack.child.outcome")
                if child_outcome == "success":
                    return Outcome(status=StageStatus.SUCCESS, notes="Child completed successfully")
                if child_status == "failed":
                    return Outcome(status=StageStatus.FAIL, failure_reason="Child pipeline failed")

            # Evaluate stop condition
            if stop_condition:
                dummy_outcome = Outcome()
                if evaluate_condition(stop_condition, dummy_outcome, context):
                    return Outcome(status=StageStatus.SUCCESS, notes="Stop condition satisfied")

            # Wait
            if "wait" in actions:
                await asyncio.sleep(poll_interval)

        return Outcome(status=StageStatus.FAIL, failure_reason=f"Max cycles exceeded ({max_cycles})")


def _parse_duration(s: str) -> float:
    """Parse duration string like '45s' or '1m' to seconds."""
    s = s.strip()
    if s.endswith("s"):
        return float(s[:-1])
    if s.endswith("m"):
        return float(s[:-1]) * 60
    try:
        return float(s)
    except ValueError:
        return 45.0
