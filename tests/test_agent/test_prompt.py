"""Tests for system prompt construction."""

import os

import pytest

from attractor_agent.prompt import (
    build_environment_context,
    build_system_prompt,
    discover_project_docs,
    MAX_PROJECT_DOCS_BYTES,
)


class TestBuildEnvironmentContext:
    def test_basic_context(self):
        ctx = build_environment_context(
            working_dir="/home/user/project",
            platform_name="linux",
            os_version="6.1.0",
        )
        assert "/home/user/project" in ctx
        assert "linux" in ctx
        assert "Is git repository: false" in ctx

    def test_with_git(self):
        ctx = build_environment_context(
            working_dir="/home/user/project",
            platform_name="linux",
            os_version="6.1.0",
            git_branch="main",
            git_status="2 modified, 1 untracked",
            git_recent_commits=["abc1234 feat: add X", "def5678 fix: Y"],
        )
        assert "Is git repository: true" in ctx
        assert "Git branch: main" in ctx
        assert "2 modified" in ctx
        assert "abc1234" in ctx

    def test_with_model_and_date(self):
        ctx = build_environment_context(
            working_dir="/w",
            platform_name="darwin",
            os_version="24.0",
            model_name="Claude Opus 4.6",
            date="2026-02-23",
        )
        assert "Claude Opus 4.6" in ctx
        assert "2026-02-23" in ctx


class TestDiscoverProjectDocs:
    def test_finds_agents_md(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("# Agent Instructions")
        docs = discover_project_docs(str(tmp_path), "anthropic")
        assert len(docs) == 1
        assert "Agent Instructions" in docs[0]

    def test_anthropic_loads_claude_md(self, tmp_path):
        (tmp_path / "CLAUDE.md").write_text("# Claude Rules")
        (tmp_path / "GEMINI.md").write_text("# Gemini Rules")
        docs = discover_project_docs(str(tmp_path), "anthropic")
        assert any("Claude Rules" in d for d in docs)
        assert not any("Gemini Rules" in d for d in docs)

    def test_gemini_loads_gemini_md(self, tmp_path):
        (tmp_path / "GEMINI.md").write_text("# Gemini Rules")
        (tmp_path / "CLAUDE.md").write_text("# Claude Rules")
        docs = discover_project_docs(str(tmp_path), "gemini")
        assert any("Gemini Rules" in d for d in docs)
        assert not any("Claude Rules" in d for d in docs)

    def test_openai_loads_codex_instructions(self, tmp_path):
        codex_dir = tmp_path / ".codex"
        codex_dir.mkdir()
        (codex_dir / "instructions.md").write_text("# Codex Rules")
        docs = discover_project_docs(str(tmp_path), "openai")
        assert any("Codex Rules" in d for d in docs)

    def test_subdirectory_precedence(self, tmp_path):
        (tmp_path / "AGENTS.md").write_text("Root instructions")
        sub = tmp_path / "src"
        sub.mkdir()
        (sub / "AGENTS.md").write_text("Subdirectory instructions")
        docs = discover_project_docs(str(sub), "anthropic", git_root=str(tmp_path))
        assert len(docs) == 2
        # Root comes first
        assert "Root" in docs[0]
        assert "Subdirectory" in docs[1]

    def test_truncation_at_32kb(self, tmp_path):
        big = "x" * 40_000
        (tmp_path / "AGENTS.md").write_text(big)
        docs = discover_project_docs(str(tmp_path), "anthropic")
        combined = "".join(docs)
        assert "truncated at 32KB" in combined

    def test_no_files_returns_empty(self, tmp_path):
        docs = discover_project_docs(str(tmp_path), "anthropic")
        assert docs == []


class TestBuildSystemPrompt:
    def test_all_five_layers(self):
        prompt = build_system_prompt(
            base_instructions="You are an assistant.",
            environment_context="<environment>\nPlatform: linux\n</environment>",
            tool_descriptions=[("read_file", "Read a file"), ("shell", "Run command")],
            project_docs=["# Project\nBuild system"],
            user_instructions="Always use Python.",
        )
        assert "You are an assistant" in prompt
        assert "Platform: linux" in prompt
        assert "read_file" in prompt
        assert "Build system" in prompt
        assert "Always use Python" in prompt

    def test_minimal_prompt(self):
        prompt = build_system_prompt(base_instructions="Base only.")
        assert prompt == "Base only."

    def test_layer_ordering(self):
        prompt = build_system_prompt(
            base_instructions="LAYER1",
            environment_context="LAYER2",
            tool_descriptions=[("t", "LAYER3")],
            project_docs=["LAYER4"],
            user_instructions="LAYER5",
        )
        pos1 = prompt.index("LAYER1")
        pos2 = prompt.index("LAYER2")
        pos3 = prompt.index("LAYER3")
        pos4 = prompt.index("LAYER4")
        pos5 = prompt.index("LAYER5")
        assert pos1 < pos2 < pos3 < pos4 < pos5
