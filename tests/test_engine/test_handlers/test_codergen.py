"""Tests for CodergenHandler."""

import json
import os
import pytest

from attractor.context import Context
from attractor.graph import Graph, Node
from attractor.handlers.codergen import CodergenHandler, expand_variables
from attractor.outcome import Outcome, StageStatus


class MockBackend:
    def __init__(self, response="Mock response"):
        self.response = response
        self.calls = []

    async def run(self, node, prompt, context):
        self.calls.append((node.id, prompt))
        return self.response


class FailingBackend:
    async def run(self, node, prompt, context):
        raise RuntimeError("Backend crashed")


class OutcomeBackend:
    async def run(self, node, prompt, context):
        return Outcome(status=StageStatus.FAIL, failure_reason="LLM said no")


class TestExpandVariables:
    def test_goal_expansion(self):
        g = Graph(goal="Build a calculator")
        ctx = Context()
        assert expand_variables("Implement $goal", g, ctx) == "Implement Build a calculator"

    def test_no_variables(self):
        g = Graph(goal="test")
        assert expand_variables("plain text", g, Context()) == "plain text"


class TestCodergenHandler:
    @pytest.mark.asyncio
    async def test_simulation_mode(self, tmp_path):
        handler = CodergenHandler(backend=None)
        node = Node(id="task1", label="Do something")
        ctx = Context()
        g = Graph(goal="test")
        outcome = await handler.execute(node, ctx, g, str(tmp_path))

        assert outcome.status == StageStatus.SUCCESS
        assert outcome.context_updates["last_stage"] == "task1"
        assert os.path.exists(tmp_path / "task1" / "prompt.md")
        assert os.path.exists(tmp_path / "task1" / "response.md")
        assert os.path.exists(tmp_path / "task1" / "status.json")

        with open(tmp_path / "task1" / "response.md") as f:
            assert "Simulated" in f.read()

    @pytest.mark.asyncio
    async def test_with_backend(self, tmp_path):
        backend = MockBackend(response="Generated code here")
        handler = CodergenHandler(backend=backend)
        node = Node(id="code", prompt="Write tests for $goal")
        ctx = Context()
        g = Graph(goal="calculator")
        outcome = await handler.execute(node, ctx, g, str(tmp_path))

        assert outcome.status == StageStatus.SUCCESS
        assert len(backend.calls) == 1
        assert backend.calls[0] == ("code", "Write tests for calculator")

        with open(tmp_path / "code" / "response.md") as f:
            assert f.read() == "Generated code here"

    @pytest.mark.asyncio
    async def test_backend_returns_outcome(self, tmp_path):
        handler = CodergenHandler(backend=OutcomeBackend())
        node = Node(id="t", label="test")
        outcome = await handler.execute(node, Context(), Graph(), str(tmp_path))

        assert outcome.status == StageStatus.FAIL
        assert outcome.failure_reason == "LLM said no"

    @pytest.mark.asyncio
    async def test_backend_exception(self, tmp_path):
        handler = CodergenHandler(backend=FailingBackend())
        node = Node(id="t", label="test")
        outcome = await handler.execute(node, Context(), Graph(), str(tmp_path))

        assert outcome.status == StageStatus.FAIL
        assert "Backend crashed" in outcome.failure_reason

    @pytest.mark.asyncio
    async def test_prompt_fallback_to_label(self, tmp_path):
        backend = MockBackend()
        handler = CodergenHandler(backend=backend)
        node = Node(id="t", label="My label prompt")
        await handler.execute(node, Context(), Graph(), str(tmp_path))

        assert backend.calls[0][1] == "My label prompt"

    @pytest.mark.asyncio
    async def test_status_json_written(self, tmp_path):
        handler = CodergenHandler(backend=None)
        node = Node(id="s", label="test")
        await handler.execute(node, Context(), Graph(), str(tmp_path))

        with open(tmp_path / "s" / "status.json") as f:
            data = json.load(f)
        assert data["status"] == "success"
