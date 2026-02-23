"""OpenAI provider profile (codex-rs-aligned)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from attractor_agent.environments.base import ExecutionEnvironment
from attractor_agent.profiles.base import BaseProfile
from attractor_agent.tools.core import (
    make_read_file_tool,
    make_write_file_tool,
    make_grep_tool,
    make_glob_tool,
    make_shell_tool,
)
from attractor_agent.tools.patch import make_apply_patch_tool
from attractor_agent.tools.registry import ToolRegistry


_BASE_INSTRUCTIONS = """\
You are an expert software engineer. You are helping the user with coding tasks.

# Tool Usage
- Use `read_file` to examine files before making changes.
- Use `apply_patch` to modify or create files using the v4a patch format.
- Use `write_file` only for creating entirely new files.
- Use `shell` for running commands. Default timeout is 10 seconds.
- Use `grep` to search file contents.
- Use `glob` to find files by pattern.

# apply_patch Format
Use the v4a patch format for all file modifications:
- `*** Add File: <path>` to create new files
- `*** Delete File: <path>` to remove files
- `*** Update File: <path>` with `@@` hunks to modify existing files
- Context lines start with a space, deletions with `-`, additions with `+`

# Best Practices
- Read files before editing them.
- Make targeted changes rather than rewriting entire files.
- Run tests after making changes.
- Write clear, maintainable code.
"""


@dataclass
class OpenAIProfile(BaseProfile):
    """OpenAI profile aligned with codex-rs toolset."""

    id: str = "openai"
    supports_reasoning: bool = True
    supports_streaming: bool = True
    supports_parallel_tool_calls: bool = True
    context_window_size: int = 200_000

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
        opts: dict[str, Any] = {}
        if self.reasoning_effort:
            opts["reasoning"] = {"effort": self.reasoning_effort}
        return opts or None


def create_openai_profile(
    model: str = "gpt-5.2-codex",
    env: ExecutionEnvironment | None = None,
    reasoning_effort: str | None = None,
) -> OpenAIProfile:
    """Create an OpenAI profile with standard tools."""
    profile = OpenAIProfile(model=model, reasoning_effort=reasoning_effort)
    if env:
        for tool in [
            make_read_file_tool(env),
            make_apply_patch_tool(env),
            make_write_file_tool(env),
            make_shell_tool(env, default_timeout_ms=10_000),
            make_grep_tool(env),
            make_glob_tool(env),
        ]:
            profile.tool_registry.register(tool, tool.execute)
    return profile
