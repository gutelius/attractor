"""Anthropic provider profile (Claude Code-aligned)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from attractor_agent.environments.base import ExecutionEnvironment
from attractor_agent.profiles.base import BaseProfile
from attractor_agent.tools.core import (
    make_read_file_tool,
    make_write_file_tool,
    make_edit_file_tool,
    make_grep_tool,
    make_glob_tool,
    make_shell_tool,
)
from attractor_agent.tools.registry import ToolRegistry


_BASE_INSTRUCTIONS = """\
You are an expert software engineer. You help users with coding tasks.

# Tool Usage
- Use `read_file` to examine files before making changes. Always read before editing.
- Use `edit_file` to make targeted changes using exact string matching.
  - The `old_string` must be unique in the file.
  - Use `replace_all=true` only when intentionally replacing every occurrence.
  - Prefer editing existing files over creating new ones.
- Use `write_file` to create new files or overwrite entire files.
- Use `shell` for running commands. Default timeout is 120 seconds.
- Use `grep` to search file contents.
- Use `glob` to find files by pattern.

# Best Practices
- Read files before editing them.
- Make targeted edits rather than rewriting entire files.
- Prefer `edit_file` over `write_file` for modifications.
- Run tests after making changes.
- Write clear, maintainable code.
"""


@dataclass
class AnthropicProfile(BaseProfile):
    """Anthropic profile aligned with Claude Code toolset."""

    id: str = "anthropic"
    supports_reasoning: bool = True
    supports_streaming: bool = True
    supports_parallel_tool_calls: bool = True
    context_window_size: int = 200_000
    beta_headers: list[str] = field(default_factory=list)

    def build_system_prompt(
        self,
        environment: dict[str, str] | None = None,
        project_docs: list[str] | None = None,
        user_instructions: str | None = None,
    ) -> str:
        return self._build_prompt_layers(
            _BASE_INSTRUCTIONS, environment, project_docs, user_instructions
        )

    def provider_options(self) -> dict[str, Any] | None:
        if self.beta_headers:
            return {"anthropic": {"beta_headers": self.beta_headers}}
        return None


def create_anthropic_profile(
    model: str = "claude-opus-4-6",
    env: ExecutionEnvironment | None = None,
    beta_headers: list[str] | None = None,
) -> AnthropicProfile:
    """Create an Anthropic profile with standard tools."""
    profile = AnthropicProfile(model=model, beta_headers=beta_headers or [])
    if env:
        for tool in [
            make_read_file_tool(env),
            make_write_file_tool(env),
            make_edit_file_tool(env),
            make_shell_tool(env, default_timeout_ms=120_000),
            make_grep_tool(env),
            make_glob_tool(env),
        ]:
            profile.tool_registry.register(tool, tool.execute)
    return profile
