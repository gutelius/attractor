"""Tests for WaitForHumanHandler."""

import pytest

from attractor.context import Context
from attractor.graph import Edge, Graph, Node
from attractor.handlers.human import WaitForHumanHandler
from attractor.interviewer import Answer, AnswerValue, QueueInterviewer
from attractor.outcome import StageStatus


def _gate_graph() -> Graph:
    return Graph(
        nodes={
            "review": Node(id="review", shape="hexagon", label="Review plan"),
            "approve": Node(id="approve"),
            "reject": Node(id="reject"),
        },
        edges=[
            Edge(source="review", target="approve", label="[A] Approve"),
            Edge(source="review", target="reject", label="[R] Reject"),
        ],
    )


class TestWaitForHumanHandler:
    @pytest.mark.asyncio
    async def test_selects_matching_choice(self):
        iv = QueueInterviewer([Answer(value="A")])
        handler = WaitForHumanHandler(iv)
        g = _gate_graph()
        outcome = await handler.execute(g.nodes["review"], Context(), g, "/tmp")

        assert outcome.status == StageStatus.SUCCESS
        assert "approve" in outcome.suggested_next_ids
        assert outcome.context_updates["human.gate.selected"] == "A"

    @pytest.mark.asyncio
    async def test_selects_second_choice(self):
        iv = QueueInterviewer([Answer(value="R")])
        handler = WaitForHumanHandler(iv)
        g = _gate_graph()
        outcome = await handler.execute(g.nodes["review"], Context(), g, "/tmp")

        assert outcome.status == StageStatus.SUCCESS
        assert "reject" in outcome.suggested_next_ids

    @pytest.mark.asyncio
    async def test_no_edges_returns_fail(self):
        iv = QueueInterviewer()
        handler = WaitForHumanHandler(iv)
        g = Graph(nodes={"gate": Node(id="gate", shape="hexagon")})
        outcome = await handler.execute(g.nodes["gate"], Context(), g, "/tmp")

        assert outcome.status == StageStatus.FAIL
        assert "No outgoing edges" in outcome.failure_reason

    @pytest.mark.asyncio
    async def test_skipped_returns_fail(self):
        iv = QueueInterviewer()  # empty queue → SKIPPED
        handler = WaitForHumanHandler(iv)
        g = _gate_graph()
        outcome = await handler.execute(g.nodes["review"], Context(), g, "/tmp")

        assert outcome.status == StageStatus.FAIL
        assert "skipped" in outcome.failure_reason

    @pytest.mark.asyncio
    async def test_timeout_no_default_returns_retry(self):
        iv = QueueInterviewer([Answer(value=AnswerValue.TIMEOUT)])
        handler = WaitForHumanHandler(iv)
        g = _gate_graph()
        outcome = await handler.execute(g.nodes["review"], Context(), g, "/tmp")

        assert outcome.status == StageStatus.RETRY
        assert "timeout" in outcome.failure_reason

    @pytest.mark.asyncio
    async def test_unrecognized_answer_falls_back_to_first(self):
        iv = QueueInterviewer([Answer(value="Z")])  # no match
        handler = WaitForHumanHandler(iv)
        g = _gate_graph()
        outcome = await handler.execute(g.nodes["review"], Context(), g, "/tmp")

        assert outcome.status == StageStatus.SUCCESS
        assert "approve" in outcome.suggested_next_ids  # first choice fallback

    @pytest.mark.asyncio
    async def test_label_fallback_for_edge_without_label(self):
        iv = QueueInterviewer([Answer(value="N")])
        handler = WaitForHumanHandler(iv)
        g = Graph(
            nodes={
                "gate": Node(id="gate", shape="hexagon", label="Pick"),
                "next": Node(id="next"),
            },
            edges=[Edge(source="gate", target="next")],  # no label
        )
        outcome = await handler.execute(g.nodes["gate"], Context(), g, "/tmp")
        assert outcome.status == StageStatus.SUCCESS
