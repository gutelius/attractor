"""Tests for Checkpoint."""

import json
import os
import pytest

from attractor.checkpoint import Checkpoint
from attractor.context import Context


class TestCheckpoint:
    def test_save_and_load(self, tmp_path):
        cp = Checkpoint(
            timestamp=1234567890.0,
            current_node="TaskA",
            completed_nodes=["Start", "TaskA"],
            node_retries={"TaskA": 2},
            context_values={"goal": "test", "count": 5},
            logs=["entry1", "entry2"],
        )
        path = str(tmp_path / "checkpoint.json")
        cp.save(path)

        loaded = Checkpoint.load(path)
        assert loaded.timestamp == 1234567890.0
        assert loaded.current_node == "TaskA"
        assert loaded.completed_nodes == ["Start", "TaskA"]
        assert loaded.node_retries == {"TaskA": 2}
        assert loaded.context_values == {"goal": "test", "count": 5}
        assert loaded.logs == ["entry1", "entry2"]

    def test_from_context(self):
        ctx = Context(values={"a": 1, "b": "hello"})
        ctx.append_log("step 1")
        cp = Checkpoint.from_context(ctx, "NodeX", ["Start", "NodeX"], {"NodeX": 1})

        assert cp.current_node == "NodeX"
        assert cp.context_values == {"a": 1, "b": "hello"}
        assert cp.logs == ["step 1"]
        assert cp.timestamp > 0

    def test_restore_context(self):
        cp = Checkpoint(
            context_values={"x": 42, "y": "test"},
            logs=["log1"],
        )
        ctx = cp.restore_context()
        assert ctx.get("x") == 42
        assert ctx.get("y") == "test"
        assert ctx.logs == ["log1"]

    def test_save_creates_directories(self, tmp_path):
        cp = Checkpoint(current_node="A")
        path = str(tmp_path / "sub" / "dir" / "checkpoint.json")
        cp.save(path)
        assert os.path.exists(path)

    def test_roundtrip_empty(self, tmp_path):
        cp = Checkpoint()
        path = str(tmp_path / "empty.json")
        cp.save(path)
        loaded = Checkpoint.load(path)
        assert loaded.current_node == ""
        assert loaded.completed_nodes == []
