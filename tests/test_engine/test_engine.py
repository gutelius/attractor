"""Tests for pipeline execution engine."""

import os
import pytest

from attractor.context import Context
from attractor.engine import EngineConfig, PipelineEngine, select_edge
from attractor.graph import Edge, Graph, Node
from attractor.interviewer import Answer, QueueInterviewer
from attractor.outcome import Outcome, StageStatus


# --- Edge selection tests ---

class TestSelectEdge:
    def test_condition_match(self):
        g = Graph(
            nodes={"A": Node(id="A"), "B": Node(id="B"), "C": Node(id="C")},
            edges=[
                Edge(source="A", target="B", condition="outcome=success"),
                Edge(source="A", target="C", condition="outcome=fail"),
            ],
        )
        outcome = Outcome(status=StageStatus.SUCCESS)
        ctx = Context()
        edge = select_edge(g.nodes["A"], outcome, ctx, g)
        assert edge.target == "B"

    def test_condition_fail_path(self):
        g = Graph(
            nodes={"A": Node(id="A"), "B": Node(id="B"), "C": Node(id="C")},
            edges=[
                Edge(source="A", target="B", condition="outcome=success"),
                Edge(source="A", target="C", condition="outcome=fail"),
            ],
        )
        outcome = Outcome(status=StageStatus.FAIL)
        edge = select_edge(g.nodes["A"], outcome, Context(), g)
        assert edge.target == "C"

    def test_preferred_label(self):
        g = Graph(
            nodes={"A": Node(id="A"), "B": Node(id="B"), "C": Node(id="C")},
            edges=[
                Edge(source="A", target="B", label="approve"),
                Edge(source="A", target="C", label="reject"),
            ],
        )
        outcome = Outcome(status=StageStatus.SUCCESS, preferred_label="reject")
        edge = select_edge(g.nodes["A"], outcome, Context(), g)
        assert edge.target == "C"

    def test_suggested_next_ids(self):
        g = Graph(
            nodes={"A": Node(id="A"), "B": Node(id="B"), "C": Node(id="C")},
            edges=[
                Edge(source="A", target="B"),
                Edge(source="A", target="C"),
            ],
        )
        outcome = Outcome(status=StageStatus.SUCCESS, suggested_next_ids=["C"])
        edge = select_edge(g.nodes["A"], outcome, Context(), g)
        assert edge.target == "C"

    def test_weight_tiebreak(self):
        g = Graph(
            nodes={"A": Node(id="A"), "B": Node(id="B"), "C": Node(id="C")},
            edges=[
                Edge(source="A", target="B", weight=1),
                Edge(source="A", target="C", weight=10),
            ],
        )
        outcome = Outcome(status=StageStatus.SUCCESS)
        edge = select_edge(g.nodes["A"], outcome, Context(), g)
        assert edge.target == "C"

    def test_lexical_tiebreak(self):
        g = Graph(
            nodes={"A": Node(id="A"), "B": Node(id="B"), "C": Node(id="C")},
            edges=[
                Edge(source="A", target="C"),
                Edge(source="A", target="B"),
            ],
        )
        outcome = Outcome(status=StageStatus.SUCCESS)
        edge = select_edge(g.nodes["A"], outcome, Context(), g)
        assert edge.target == "B"  # B < C lexically

    def test_no_edges(self):
        g = Graph(nodes={"A": Node(id="A")})
        assert select_edge(g.nodes["A"], Outcome(), Context(), g) is None


# --- Full engine tests ---

def _linear_dot():
    return '''
    digraph G {
        Start [shape=Mdiamond]
        Task [label="Do work"]
        Exit [shape=Msquare]
        Start -> Task -> Exit
    }
    '''


def _branching_dot():
    return '''
    digraph G {
        Start [shape=Mdiamond]
        Check [shape=diamond]
        Good [label="Good path"]
        Bad [label="Bad path"]
        Exit [shape=Msquare]
        Start -> Check
        Check -> Good [condition="outcome=success"]
        Check -> Bad [condition="outcome=fail"]
        Good -> Exit
        Bad -> Exit
    }
    '''


class TestPipelineEngine:
    @pytest.mark.asyncio
    async def test_linear_pipeline(self, tmp_path):
        config = EngineConfig(logs_root=str(tmp_path), checkpoint_enabled=True)
        engine = PipelineEngine(config)
        outcome = await engine.run_dot(_linear_dot())

        assert outcome.status == StageStatus.SUCCESS
        assert len(engine.events) > 0
        # Checkpoint should exist
        assert os.path.exists(tmp_path / "checkpoint.json")

    @pytest.mark.asyncio
    async def test_dry_run(self, tmp_path):
        config = EngineConfig(logs_root=str(tmp_path), dry_run=True)
        engine = PipelineEngine(config)
        outcome = await engine.run_dot(_linear_dot())
        assert outcome.status == StageStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_branching_pipeline(self, tmp_path):
        config = EngineConfig(logs_root=str(tmp_path))
        engine = PipelineEngine(config)
        outcome = await engine.run_dot(_branching_dot())
        assert outcome.status == StageStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_conditional_routing(self, tmp_path):
        dot = '''
        digraph G {
            Start [shape=Mdiamond]
            Plan [label="Plan work"]
            Review [shape=hexagon, label="Review plan"]
            Implement [label="Write code"]
            Revise [label="Revise plan"]
            Exit [shape=Msquare]
            Start -> Plan -> Review
            Review -> Implement [label="approve", condition="outcome=success"]
            Review -> Revise [label="revise", condition="outcome=fail"]
            Implement -> Exit
            Revise -> Plan
        }
        '''
        iv = QueueInterviewer([Answer(value="A")])  # auto-approve first option
        config = EngineConfig(logs_root=str(tmp_path), interviewer=iv)
        engine = PipelineEngine(config)
        outcome = await engine.run_dot(dot)
        assert outcome.status == StageStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_goal_gate_enforcement(self, tmp_path):
        """Goal gate with retry_target jumps back when gate fails."""

        class FailThenSucceedBackend:
            def __init__(self):
                self.impl_calls = 0

            async def run(self, node, prompt, context):
                if node.id == "Implement":
                    self.impl_calls += 1
                    if self.impl_calls <= 1:
                        return Outcome(status=StageStatus.FAIL, failure_reason="first attempt fails")
                return f"Success for {node.id}"

        backend = FailThenSucceedBackend()
        # Use run() directly with a pre-built graph to avoid validation on loop edges
        from attractor.parser import parse_dot
        graph = parse_dot('''
        digraph G {
            Start [shape=Mdiamond]
            Plan [label="Plan"]
            Implement [label="Code", goal_gate=true, retry_target="Plan"]
            Exit [shape=Msquare]
            Start -> Plan -> Implement -> Exit
        }
        ''')
        config = EngineConfig(logs_root=str(tmp_path), codergen_backend=backend, max_steps=20)
        engine = PipelineEngine(config)
        outcome = await engine.run(graph)

        assert outcome.status == StageStatus.SUCCESS
        # Should have retried via goal gate
        gate_events = [e for e in engine.events if e.kind == "goal_gate.retry"]
        assert len(gate_events) >= 1

    @pytest.mark.asyncio
    async def test_max_steps_limit(self, tmp_path):
        # Build graph directly to avoid validation error on loop back edges
        from attractor.parser import parse_dot
        graph = parse_dot('''
        digraph G {
            Start [shape=Mdiamond]
            A [label="Loop A"]
            B [label="Loop B"]
            Exit [shape=Msquare]
            Start -> A -> B -> A
        }
        ''')
        config = EngineConfig(logs_root=str(tmp_path), max_steps=10)
        engine = PipelineEngine(config)
        outcome = await engine.run(graph)
        # Should stop due to max_steps, not crash
        assert len(engine.events) > 0

    @pytest.mark.asyncio
    async def test_events_emitted(self, tmp_path):
        config = EngineConfig(logs_root=str(tmp_path))
        engine = PipelineEngine(config)
        await engine.run_dot(_linear_dot())

        kinds = [e.kind for e in engine.events]
        assert "pipeline.start" in kinds
        assert "node.start" in kinds
        assert "node.complete" in kinds

    @pytest.mark.asyncio
    async def test_loop_restart(self, tmp_path):
        # Build graph directly to bypass start_no_incoming validation
        from attractor.parser import parse_dot
        graph = parse_dot('''
        digraph G {
            Start [shape=Mdiamond]
            A [label="Task A"]
            B [label="Task B"]
            Exit [shape=Msquare]
            Start -> A -> B
            B -> Start [loop_restart=true, condition="outcome=fail"]
            B -> Exit [condition="outcome=success"]
        }
        ''')
        config = EngineConfig(logs_root=str(tmp_path), max_steps=20)
        engine = PipelineEngine(config)
        outcome = await engine.run(graph)
        # In simulation mode, all succeed, so no loop_restart triggered
        assert outcome.status == StageStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_resume_from_checkpoint(self, tmp_path):
        from attractor.checkpoint import Checkpoint

        dot = '''
        digraph G {
            Start [shape=Mdiamond]
            A [label="Task A"]
            B [label="Task B"]
            Exit [shape=Msquare]
            Start -> A -> B -> Exit
        }
        '''
        from attractor.parser import parse_dot
        from attractor.validator import validate_or_raise

        graph = parse_dot(dot)
        validate_or_raise(graph)

        # Create checkpoint as if Start and A completed
        cp = Checkpoint(
            current_node="A",
            completed_nodes=["Start", "A"],
            node_retries={},
            context_values={"pipeline.name": "G", "goal": ""},
        )

        config = EngineConfig(logs_root=str(tmp_path))
        engine = PipelineEngine(config)
        outcome = await engine.run(graph, resume_from=cp)
        assert outcome.status == StageStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_no_start_node_fails(self, tmp_path):
        graph = Graph(nodes={"A": Node(id="A")})
        config = EngineConfig(logs_root=str(tmp_path))
        engine = PipelineEngine(config)
        outcome = await engine.run(graph)
        assert outcome.status == StageStatus.FAIL

    @pytest.mark.asyncio
    async def test_retry_logic(self, tmp_path):
        """Node with max_retries retries on RETRY status."""
        call_count = 0

        class RetryBackend:
            async def run(self, node, prompt, context):
                nonlocal call_count
                call_count += 1
                if node.id == "Task" and call_count < 3:
                    return Outcome(status=StageStatus.RETRY, failure_reason="not ready")
                return f"Done: {node.id}"

        dot = '''
        digraph G {
            Start [shape=Mdiamond]
            Task [label="Retry task", max_retries=5]
            Exit [shape=Msquare]
            Start -> Task -> Exit
        }
        '''
        config = EngineConfig(logs_root=str(tmp_path), codergen_backend=RetryBackend())
        engine = PipelineEngine(config)
        outcome = await engine.run_dot(dot)
        assert outcome.status == StageStatus.SUCCESS
        assert call_count >= 3
