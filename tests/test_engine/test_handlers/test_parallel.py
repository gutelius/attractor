"""Tests for ParallelHandler and FanInHandler."""

import json
import pytest

from attractor.context import Context
from attractor.graph import Edge, Graph, Node
from attractor.handlers.parallel import BranchResult, FanInHandler, ParallelHandler
from attractor.outcome import Outcome, StageStatus


def _parallel_graph() -> Graph:
    return Graph(
        nodes={
            "fan": Node(id="fan", shape="component"),
            "A": Node(id="A"),
            "B": Node(id="B"),
            "C": Node(id="C"),
        },
        edges=[
            Edge(source="fan", target="A"),
            Edge(source="fan", target="B"),
            Edge(source="fan", target="C"),
        ],
    )


class TestParallelHandler:
    @pytest.mark.asyncio
    async def test_simulation_mode(self):
        handler = ParallelHandler(branch_executor=None)
        g = _parallel_graph()
        ctx = Context()
        outcome = await handler.execute(g.nodes["fan"], ctx, g, "/tmp")

        assert outcome.status == StageStatus.SUCCESS
        assert ctx.get("parallel.results") is not None

    @pytest.mark.asyncio
    async def test_no_branches_fails(self):
        handler = ParallelHandler()
        g = Graph(nodes={"fan": Node(id="fan", shape="component")})
        outcome = await handler.execute(g.nodes["fan"], Context(), g, "/tmp")
        assert outcome.status == StageStatus.FAIL

    @pytest.mark.asyncio
    async def test_with_executor_all_succeed(self):
        async def executor(node_id, ctx, graph, logs):
            return Outcome(status=StageStatus.SUCCESS, notes=f"done-{node_id}")

        handler = ParallelHandler(branch_executor=executor)
        g = _parallel_graph()
        ctx = Context()
        outcome = await handler.execute(g.nodes["fan"], ctx, g, "/tmp")

        assert outcome.status == StageStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_with_executor_some_fail(self):
        call_count = 0

        async def executor(node_id, ctx, graph, logs):
            nonlocal call_count
            call_count += 1
            if node_id == "B":
                return Outcome(status=StageStatus.FAIL, failure_reason="B failed")
            return Outcome(status=StageStatus.SUCCESS)

        handler = ParallelHandler(branch_executor=executor)
        g = _parallel_graph()
        ctx = Context()
        outcome = await handler.execute(g.nodes["fan"], ctx, g, "/tmp")

        assert outcome.status == StageStatus.PARTIAL_SUCCESS

    @pytest.mark.asyncio
    async def test_first_success_policy(self):
        async def executor(node_id, ctx, graph, logs):
            if node_id == "A":
                return Outcome(status=StageStatus.SUCCESS)
            return Outcome(status=StageStatus.FAIL)

        handler = ParallelHandler(branch_executor=executor)
        g = _parallel_graph()
        g.nodes["fan"].extra["join_policy"] = "first_success"
        outcome = await handler.execute(g.nodes["fan"], Context(), g, "/tmp")
        assert outcome.status == StageStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_k_of_n_policy(self):
        async def executor(node_id, ctx, graph, logs):
            if node_id in ("A", "B"):
                return Outcome(status=StageStatus.SUCCESS)
            return Outcome(status=StageStatus.FAIL)

        handler = ParallelHandler(branch_executor=executor)
        g = _parallel_graph()
        g.nodes["fan"].extra["join_policy"] = "k_of_n"
        g.nodes["fan"].extra["k"] = "2"
        outcome = await handler.execute(g.nodes["fan"], Context(), g, "/tmp")
        assert outcome.status == StageStatus.SUCCESS


class TestFanInHandler:
    @pytest.mark.asyncio
    async def test_selects_best_by_status(self):
        handler = FanInHandler()
        ctx = Context()
        results = [
            {"node_id": "A", "status": "fail", "score": 10},
            {"node_id": "B", "status": "success", "score": 5},
            {"node_id": "C", "status": "partial_success", "score": 8},
        ]
        ctx.set("parallel.results", json.dumps(results))
        g = Graph(nodes={"fin": Node(id="fin", shape="tripleoctagon")})

        outcome = await handler.execute(g.nodes["fin"], ctx, g, "/tmp")
        assert outcome.status == StageStatus.SUCCESS
        assert outcome.context_updates["parallel.fan_in.best_id"] == "B"

    @pytest.mark.asyncio
    async def test_score_tiebreak(self):
        handler = FanInHandler()
        ctx = Context()
        results = [
            {"node_id": "A", "status": "success", "score": 5},
            {"node_id": "B", "status": "success", "score": 10},
        ]
        ctx.set("parallel.results", json.dumps(results))
        g = Graph(nodes={"fin": Node(id="fin")})

        outcome = await handler.execute(g.nodes["fin"], ctx, g, "/tmp")
        assert outcome.context_updates["parallel.fan_in.best_id"] == "B"

    @pytest.mark.asyncio
    async def test_no_results_fails(self):
        handler = FanInHandler()
        outcome = await handler.execute(Node(id="fin"), Context(), Graph(), "/tmp")
        assert outcome.status == StageStatus.FAIL

    @pytest.mark.asyncio
    async def test_empty_results_fails(self):
        handler = FanInHandler()
        ctx = Context()
        ctx.set("parallel.results", json.dumps([]))
        outcome = await handler.execute(Node(id="fin"), ctx, Graph(), "/tmp")
        assert outcome.status == StageStatus.FAIL
