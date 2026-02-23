"""Tests for provider profiles."""

import pytest

from attractor_agent.environments.local import LocalExecutionEnvironment
from attractor_agent.profiles.openai import OpenAIProfile, create_openai_profile
from attractor_agent.profiles.anthropic import AnthropicProfile, create_anthropic_profile
from attractor_agent.profiles.gemini import GeminiProfile, create_gemini_profile


@pytest.fixture
def env(tmp_path):
    return LocalExecutionEnvironment(working_dir=str(tmp_path))


class TestOpenAIProfile:
    def test_default_fields(self):
        p = OpenAIProfile()
        assert p.id == "openai"
        assert p.supports_reasoning is True
        assert p.supports_streaming is True

    def test_create_with_env(self, env):
        p = create_openai_profile(env=env)
        tool_names = {t.name for t in p.tools()}
        assert "read_file" in tool_names
        assert "apply_patch" in tool_names
        assert "write_file" in tool_names
        assert "shell" in tool_names
        assert "grep" in tool_names
        assert "glob" in tool_names
        # OpenAI does NOT have edit_file
        assert "edit_file" not in tool_names

    def test_system_prompt_has_five_layers(self, env):
        p = create_openai_profile(env=env)
        prompt = p.build_system_prompt(
            environment={"platform": "linux", "cwd": "/home/user"},
            project_docs=["# Project\nThis is a test project."],
            user_instructions="Always use TypeScript.",
        )
        assert "apply_patch" in prompt  # Layer 1: base instructions
        assert "platform" in prompt      # Layer 2: environment
        assert "Available Tools" in prompt  # Layer 3: tool descriptions
        assert "test project" in prompt  # Layer 4: project docs
        assert "TypeScript" in prompt    # Layer 5: user instructions

    def test_provider_options_reasoning(self):
        p = OpenAIProfile(reasoning_effort="high")
        opts = p.provider_options()
        assert opts == {"reasoning": {"effort": "high"}}

    def test_provider_options_none(self):
        p = OpenAIProfile()
        assert p.provider_options() is None


class TestAnthropicProfile:
    def test_default_fields(self):
        p = AnthropicProfile()
        assert p.id == "anthropic"
        assert p.supports_reasoning is True

    def test_create_with_env(self, env):
        p = create_anthropic_profile(env=env)
        tool_names = {t.name for t in p.tools()}
        assert "read_file" in tool_names
        assert "write_file" in tool_names
        assert "edit_file" in tool_names
        assert "shell" in tool_names
        assert "grep" in tool_names
        assert "glob" in tool_names
        # Anthropic does NOT have apply_patch
        assert "apply_patch" not in tool_names

    def test_system_prompt_mentions_edit_file(self, env):
        p = create_anthropic_profile(env=env)
        prompt = p.build_system_prompt()
        assert "edit_file" in prompt
        assert "old_string" in prompt

    def test_provider_options_beta(self):
        p = AnthropicProfile(beta_headers=["extended-thinking-2025-01-24"])
        opts = p.provider_options()
        assert opts == {"anthropic": {"beta_headers": ["extended-thinking-2025-01-24"]}}

    def test_provider_options_none(self):
        p = AnthropicProfile()
        assert p.provider_options() is None


class TestGeminiProfile:
    def test_default_fields(self):
        p = GeminiProfile()
        assert p.id == "gemini"
        assert p.context_window_size == 1_000_000

    def test_create_with_env(self, env):
        p = create_gemini_profile(env=env)
        tool_names = {t.name for t in p.tools()}
        assert "read_file" in tool_names
        assert "read_many_files" in tool_names
        assert "write_file" in tool_names
        assert "edit_file" in tool_names
        assert "shell" in tool_names
        assert "grep" in tool_names
        assert "glob" in tool_names
        assert "list_dir" in tool_names

    def test_system_prompt_mentions_gemini(self, env):
        p = create_gemini_profile(env=env)
        prompt = p.build_system_prompt()
        assert "GEMINI.md" in prompt

    def test_provider_options_safety(self):
        p = GeminiProfile(safety_settings={"harm": "block_none"})
        opts = p.provider_options()
        assert opts == {"gemini": {"safety_settings": {"harm": "block_none"}}}

    def test_provider_options_none(self):
        p = GeminiProfile()
        assert p.provider_options() is None

    async def test_read_many_files(self, env, tmp_path):
        (tmp_path / "a.txt").write_text("aaa")
        (tmp_path / "b.txt").write_text("bbb")
        p = create_gemini_profile(env=env)
        tool = p.tool_registry.get("read_many_files")
        result = await tool.executor(file_paths=["a.txt", "b.txt"])
        assert "aaa" in result
        assert "bbb" in result

    async def test_list_dir(self, env, tmp_path):
        (tmp_path / "file.txt").write_text("x")
        (tmp_path / "subdir").mkdir()
        p = create_gemini_profile(env=env)
        tool = p.tool_registry.get("list_dir")
        result = await tool.executor(path=".")
        assert "file.txt" in result
        assert "subdir" in result
