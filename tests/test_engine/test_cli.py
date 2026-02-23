"""Tests for CLI entry point."""

import os

import pytest
from click.testing import CliRunner

from attractor.cli import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def simple_dot(tmp_path):
    dot = '''
    digraph G {
        Start [shape=Mdiamond]
        Task [label="Do work"]
        Exit [shape=Msquare]
        Start -> Task -> Exit
    }
    '''
    p = tmp_path / "simple.dot"
    p.write_text(dot)
    return str(p)


@pytest.fixture
def invalid_dot(tmp_path):
    dot = '''
    digraph G {
        A [label="No start or exit"]
    }
    '''
    p = tmp_path / "invalid.dot"
    p.write_text(dot)
    return str(p)


class TestRunCommand:
    def test_run_dry_run(self, runner, simple_dot, tmp_path):
        log_dir = str(tmp_path / "logs")
        result = runner.invoke(main, ["run", simple_dot, "--dry-run", "--log-dir", log_dir])
        assert result.exit_code == 0
        assert "completed" in result.output.lower() or "success" in result.output.lower()

    def test_run_with_goal(self, runner, simple_dot, tmp_path):
        result = runner.invoke(main, ["run", simple_dot, "--dry-run", "--goal", "test goal",
                                       "--log-dir", str(tmp_path / "logs")])
        assert result.exit_code == 0

    def test_run_invalid_file(self, runner):
        result = runner.invoke(main, ["run", "/nonexistent/file.dot"])
        assert result.exit_code != 0

    def test_run_invalid_graph(self, runner, invalid_dot, tmp_path):
        result = runner.invoke(main, ["run", invalid_dot, "--log-dir", str(tmp_path / "logs")])
        assert result.exit_code != 0
        assert "validation failed" in result.output.lower() or "error" in result.output.lower()


class TestValidateCommand:
    def test_validate_valid(self, runner, simple_dot):
        result = runner.invoke(main, ["validate", simple_dot])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_invalid(self, runner, invalid_dot):
        result = runner.invoke(main, ["validate", invalid_dot])
        assert result.exit_code != 0
        assert "error" in result.output.lower()

    def test_validate_nonexistent(self, runner):
        result = runner.invoke(main, ["validate", "/nonexistent/file.dot"])
        assert result.exit_code != 0


class TestResumeCommand:
    def test_resume_from_checkpoint(self, runner, simple_dot, tmp_path):
        from attractor.checkpoint import Checkpoint
        cp = Checkpoint(
            current_node="Start",
            completed_nodes=["Start"],
            node_retries={},
            context_values={"pipeline.name": "G", "goal": ""},
        )
        cp_path = str(tmp_path / "checkpoint.json")
        cp.save(cp_path)

        result = runner.invoke(main, ["resume", cp_path, simple_dot,
                                       "--log-dir", str(tmp_path / "logs")])
        assert result.exit_code == 0
        assert "resumed" in result.output.lower() or "completed" in result.output.lower()

    def test_resume_nonexistent_checkpoint(self, runner, simple_dot):
        result = runner.invoke(main, ["resume", "/nonexistent/cp.json", simple_dot])
        assert result.exit_code != 0


class TestServeCommand:
    def test_serve_missing_uvicorn(self, runner, monkeypatch):
        """Test serve command when uvicorn is missing."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "uvicorn":
                raise ImportError("no uvicorn")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        result = runner.invoke(main, ["serve"])
        assert result.exit_code != 0
