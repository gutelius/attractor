"""Parallel fan-out and fan-in handlers."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from attractor.context import Context
from attractor.graph import Graph, Node
from attractor.outcome import Outcome, StageStatus

_OUTCOME_RANK = {
    StageStatus.SUCCESS: 0,
    StageStatus.PARTIAL_SUCCESS: 1,
    StageStatus.RETRY: 2,
    StageStatus.FAIL: 3,
    StageStatus.SKIPPED: 4,
}


class BranchResult:
    """Result of a parallel branch execution."""

    def __init__(self, node_id: str, outcome: Outcome, score: float = 0.0) -> None:
        self.node_id = node_id
        self.outcome = outcome
        self.score = score

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "status": self.outcome.status.value,
            "notes": self.outcome.notes,
            "score": self.score,
        }


class ParallelHandler:
    """Fans out to multiple branches concurrently.

    Requires a branch_executor callback to actually run sub-pipelines.
    """

    def __init__(self, branch_executor: Any = None) -> None:
        self.branch_executor = branch_executor

    async def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        branches = graph.outgoing_edges(node.id)
        if not branches:
            return Outcome(status=StageStatus.FAIL, failure_reason="No branches for parallel node")

        join_policy = node.extra.get("join_policy", "wait_all")
        error_policy = node.extra.get("error_policy", "continue")
        max_parallel = int(node.extra.get("max_parallel", 4))

        if self.branch_executor is None:
            # Simulation mode
            results = [
                BranchResult(e.target, Outcome(status=StageStatus.SUCCESS, notes=f"Simulated: {e.target}"))
                for e in branches
            ]
        else:
            semaphore = asyncio.Semaphore(max_parallel)
            results: list[BranchResult] = []

            async def run_branch(edge):
                async with semaphore:
                    branch_context = context.clone()
                    outcome = await self.branch_executor(edge.target, branch_context, graph, logs_root)
                    return BranchResult(edge.target, outcome)

            tasks = [asyncio.create_task(run_branch(e)) for e in branches]

            if error_policy == "fail_fast":
                for coro in asyncio.as_completed(tasks):
                    result = await coro
                    results.append(result)
                    if result.outcome.status == StageStatus.FAIL:
                        for t in tasks:
                            t.cancel()
                        break
            else:
                results = await asyncio.gather(*tasks)

        # Evaluate join policy
        success_count = sum(1 for r in results if r.outcome.is_success)
        fail_count = sum(1 for r in results if r.outcome.status == StageStatus.FAIL)

        # Store results for fan-in
        context.set("parallel.results", json.dumps([r.to_dict() for r in results]))

        if join_policy == "wait_all":
            if fail_count == 0:
                return Outcome(status=StageStatus.SUCCESS, notes=f"All {len(results)} branches succeeded")
            return Outcome(status=StageStatus.PARTIAL_SUCCESS,
                           notes=f"{success_count}/{len(results)} branches succeeded")

        if join_policy == "first_success":
            if success_count > 0:
                return Outcome(status=StageStatus.SUCCESS, notes="At least one branch succeeded")
            return Outcome(status=StageStatus.FAIL, failure_reason="All branches failed")

        if join_policy == "k_of_n":
            k = int(node.extra.get("k", 1))
            if success_count >= k:
                return Outcome(status=StageStatus.SUCCESS,
                               notes=f"{success_count}/{len(results)} branches succeeded (required {k})")
            return Outcome(status=StageStatus.FAIL,
                           failure_reason=f"Only {success_count}/{len(results)} succeeded (required {k})")

        return Outcome(status=StageStatus.SUCCESS)


class FanInHandler:
    """Consolidates results from a parallel node and selects the best."""

    async def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        raw = context.get("parallel.results")
        if not raw:
            return Outcome(status=StageStatus.FAIL, failure_reason="No parallel results to evaluate")

        try:
            results = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            return Outcome(status=StageStatus.FAIL, failure_reason="Invalid parallel results format")

        if not results:
            return Outcome(status=StageStatus.FAIL, failure_reason="Empty parallel results")

        # Heuristic selection: rank by status, then by score
        rank_map = {"success": 0, "partial_success": 1, "retry": 2, "fail": 3, "skipped": 4}
        sorted_results = sorted(
            results,
            key=lambda r: (rank_map.get(r.get("status", "fail"), 99), -r.get("score", 0), r.get("node_id", "")),
        )
        best = sorted_results[0]

        return Outcome(
            status=StageStatus.SUCCESS,
            context_updates={
                "parallel.fan_in.best_id": best.get("node_id", ""),
                "parallel.fan_in.best_outcome": best.get("status", ""),
            },
            notes=f"Selected best candidate: {best.get('node_id', 'unknown')}",
        )
