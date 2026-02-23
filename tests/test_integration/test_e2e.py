"""End-to-end integration tests."""

import os

import pytest

from attractor.checkpoint import Checkpoint
from attractor.engine import EngineConfig, PipelineEngine
from attractor.interviewer import Answer, AnswerValue, QueueInterviewer
from attractor.outcome import Outcome, StageStatus
from attractor.parser import parse_dot
from attractor.transforms import VariableExpansionTransform, StylesheetTransform
from attractor.validator import validate_or_raise


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_dot(name: str) -> str:
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


class TestSimplePipeline:
    @pytest.mark.asyncio
    async def test_full_lifecycle(self, tmp_path):
        """PARSE -> VALIDATE -> TRANSFORM -> EXECUTE -> FINALIZE."""
        dot = _load_dot("simple.dot")
        graph = parse_dot(dot)
        graph = VariableExpansionTransform().apply(graph)
        graph = StylesheetTransform().apply(graph)
        validate_or_raise(graph)

        config = EngineConfig(logs_root=str(tmp_path), checkpoint_enabled=True)
        engine = PipelineEngine(config)
        outcome = await engine.run(graph)

        assert outcome.status == StageStatus.SUCCESS
        assert len(engine.events) > 0
        # Checkpoint written
        assert os.path.exists(tmp_path / "checkpoint.json")

    @pytest.mark.asyncio
    async def test_dry_run(self, tmp_path):
        dot = _load_dot("simple.dot")
        config = EngineConfig(logs_root=str(tmp_path), dry_run=True)
        engine = PipelineEngine(config)
        outcome = await engine.run_dot(dot)
        assert outcome.status == StageStatus.SUCCESS
        # Events contain dry-run markers
        notes = [e.data.get("status") for e in engine.events if e.kind == "node.complete"]
        assert all(s == "success" for s in notes)

    @pytest.mark.asyncio
    async def test_run_dot_convenience(self, tmp_path):
        dot = _load_dot("simple.dot")
        config = EngineConfig(logs_root=str(tmp_path))
        engine = PipelineEngine(config)
        outcome = await engine.run_dot(dot)
        assert outcome.status == StageStatus.SUCCESS


class TestBranchingPipeline:
    @pytest.mark.asyncio
    async def test_conditional_routing(self, tmp_path):
        dot = _load_dot("branching.dot")
        config = EngineConfig(logs_root=str(tmp_path))
        engine = PipelineEngine(config)
        outcome = await engine.run_dot(dot)
        assert outcome.status == StageStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_goal_preserved(self, tmp_path):
        dot = _load_dot("branching.dot")
        graph = parse_dot(dot)
        assert graph.goal == "Complete the review process"


class TestHumanInTheLoop:
    @pytest.mark.asyncio
    async def test_approve_path(self, tmp_path):
        dot = _load_dot("human_review.dot")
        graph = parse_dot(dot)
        graph = VariableExpansionTransform().apply(graph)
        graph = StylesheetTransform().apply(graph)
        # Auto-approve (first option = approve)
        iv = QueueInterviewer([Answer(value="A")])
        config = EngineConfig(logs_root=str(tmp_path), interviewer=iv)
        engine = PipelineEngine(config)
        outcome = await engine.run(graph)
        assert outcome.status == StageStatus.SUCCESS


class TestCheckpointResume:
    @pytest.mark.asyncio
    async def test_resume_mid_pipeline(self, tmp_path):
        dot = _load_dot("simple.dot")
        graph = parse_dot(dot)
        graph = VariableExpansionTransform().apply(graph)
        graph = StylesheetTransform().apply(graph)
        validate_or_raise(graph)

        # Create checkpoint as if Start completed
        cp = Checkpoint(
            current_node="Start",
            completed_nodes=["Start"],
            node_retries={},
            context_values={"pipeline.name": "SimplePipeline", "goal": ""},
        )

        config = EngineConfig(logs_root=str(tmp_path))
        engine = PipelineEngine(config)
        outcome = await engine.run(graph, resume_from=cp)
        assert outcome.status == StageStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_checkpoint_roundtrip(self, tmp_path):
        """Run a pipeline, save checkpoint, load it back."""
        dot = _load_dot("simple.dot")
        config = EngineConfig(logs_root=str(tmp_path), checkpoint_enabled=True)
        engine = PipelineEngine(config)
        await engine.run_dot(dot)

        cp_path = str(tmp_path / "checkpoint.json")
        assert os.path.exists(cp_path)
        cp = Checkpoint.load(cp_path)
        assert len(cp.completed_nodes) > 0


class TestCustomBackend:
    @pytest.mark.asyncio
    async def test_backend_receives_calls(self, tmp_path):
        """CodergenBackend gets called for non-structural nodes."""
        calls = []

        class TrackingBackend:
            async def run(self, node, prompt, context):
                calls.append(node.id)
                return f"Done: {node.id}"

        dot = _load_dot("simple.dot")
        config = EngineConfig(
            logs_root=str(tmp_path),
            codergen_backend=TrackingBackend(),
        )
        engine = PipelineEngine(config)
        outcome = await engine.run_dot(dot)
        assert outcome.status == StageStatus.SUCCESS
        # Non-start/exit nodes should have been called
        assert "Plan" in calls
        assert "Implement" in calls


class TestObservabilityEvents:
    @pytest.mark.asyncio
    async def test_event_kinds(self, tmp_path):
        dot = _load_dot("simple.dot")
        config = EngineConfig(logs_root=str(tmp_path))
        engine = PipelineEngine(config)
        await engine.run_dot(dot)

        kinds = {e.kind for e in engine.events}
        assert "pipeline.start" in kinds
        assert "node.start" in kinds
        assert "node.complete" in kinds
        assert "pipeline.finalize" in kinds

    @pytest.mark.asyncio
    async def test_events_have_timestamps(self, tmp_path):
        dot = _load_dot("simple.dot")
        config = EngineConfig(logs_root=str(tmp_path))
        engine = PipelineEngine(config)
        await engine.run_dot(dot)
        for event in engine.events:
            assert event.timestamp > 0
