"""Gemini provider profile (gemini-cli-aligned)."""

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
from attractor_llm.types import ToolDefinition


_BASE_INSTRUCTIONS = """\
You are an expert software engineer. You help users with coding tasks.

# Tool Usage
- Use `read_file` or `read_many_files` to examine files.
- Use `edit_file` for targeted modifications.
- Use `write_file` for creating new files.
- Use `shell` for running commands. Default timeout is 10 seconds.
- Use `grep` to search file contents.
- Use `glob` to find files by pattern.
- Use `list_dir` to browse directory contents.

# Best Practices
- Read files before editing them.
- Make targeted edits rather than rewriting entire files.
- Check GEMINI.md for project-specific instructions.
- Run tests after making changes.
- Write clear, maintainable code.
"""


def _make_read_many_files_tool(env: ExecutionEnvironment) -> ToolDefinition:
    """Create a read_many_files tool for batch file reading."""

    async def execute(file_paths: list[str]) -> str:
        results = []
        for path in file_paths:
            try:
                content = await env.read_file(path)
                results.append(f"=== {path} ===\n{content}")
            except Exception as e:
                results.append(f"=== {path} ===\nError: {e}")
        return "\n\n".join(results)

    return ToolDefinition(
        name="read_many_files",
        description="Read multiple files at once, returning their contents.",
        parameters={
            "type": "object",
            "properties": {
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths to read",
                },
            },
            "required": ["file_paths"],
        },
        execute=execute,
    )


def _make_list_dir_tool(env: ExecutionEnvironment) -> ToolDefinition:
    """Create a list_dir tool for directory browsing."""

    async def execute(path: str = ".", depth: int = 1) -> str:
        entries = await env.list_directory(path, depth=depth)
        lines = []
        for e in entries:
            prefix = "[dir] " if e.is_dir else "      "
            size_str = f" ({e.size} bytes)" if e.size is not None else ""
            lines.append(f"{prefix}{e.name}{size_str}")
        return "\n".join(lines) if lines else "(empty directory)"

    return ToolDefinition(
        name="list_dir",
        description="List directory contents with optional depth.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path", "default": "."},
                "depth": {"type": "integer", "description": "Recursion depth (default 1)", "default": 1},
            },
        },
        execute=execute,
    )


@dataclass
class GeminiProfile(BaseProfile):
    """Gemini profile aligned with gemini-cli toolset."""

    id: str = "gemini"
    supports_reasoning: bool = False
    supports_streaming: bool = True
    supports_parallel_tool_calls: bool = True
    context_window_size: int = 1_000_000
    safety_settings: dict[str, Any] = field(default_factory=dict)

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
        if self.safety_settings:
            return {"gemini": {"safety_settings": self.safety_settings}}
        return None


def create_gemini_profile(
    model: str = "gemini-3-flash",
    env: ExecutionEnvironment | None = None,
    safety_settings: dict[str, Any] | None = None,
) -> GeminiProfile:
    """Create a Gemini profile with standard tools."""
    profile = GeminiProfile(model=model, safety_settings=safety_settings or {})
    if env:
        for tool in [
            make_read_file_tool(env),
            _make_read_many_files_tool(env),
            make_write_file_tool(env),
            make_edit_file_tool(env),
            make_shell_tool(env, default_timeout_ms=10_000),
            make_grep_tool(env),
            make_glob_tool(env),
            _make_list_dir_tool(env),
        ]:
            profile.tool_registry.register(tool, tool.execute)
    return profile
