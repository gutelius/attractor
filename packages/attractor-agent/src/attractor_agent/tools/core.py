"""Core tool definitions and executors for the coding agent."""

from __future__ import annotations

from attractor_agent.environments.base import ExecutionEnvironment
from attractor_agent.tools.truncation import truncate_output
from attractor_llm.types import ToolDefinition


def make_read_file_tool(env: ExecutionEnvironment) -> ToolDefinition:
    """Create a read_file tool bound to an environment."""

    async def execute(file_path: str, offset: int | None = None, limit: int | None = None) -> str:
        content = await env.read_file(file_path, offset=offset, limit=limit)
        # Add line numbers
        lines = content.splitlines(keepends=True)
        start = (offset or 1)
        numbered = []
        for i, line in enumerate(lines):
            numbered.append(f"{start + i:6d}\t{line}")
        result = "".join(numbered)
        return truncate_output(result, "read_file").text

    return ToolDefinition(
        name="read_file",
        description="Read a file from the filesystem. Returns line-numbered content.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file to read"},
                "offset": {"type": "integer", "description": "Line number to start reading from (1-based)"},
                "limit": {"type": "integer", "description": "Number of lines to read"},
            },
            "required": ["file_path"],
        },
        execute=execute,
    )


def make_write_file_tool(env: ExecutionEnvironment) -> ToolDefinition:
    """Create a write_file tool bound to an environment."""

    async def execute(file_path: str, content: str) -> str:
        await env.write_file(file_path, content)
        lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        return f"Written {len(content)} bytes ({lines} lines) to {file_path}"

    return ToolDefinition(
        name="write_file",
        description="Write content to a file, creating parent directories as needed.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file to write"},
                "content": {"type": "string", "description": "Content to write to the file"},
            },
            "required": ["file_path", "content"],
        },
        execute=execute,
    )


def make_edit_file_tool(env: ExecutionEnvironment) -> ToolDefinition:
    """Create an edit_file tool bound to an environment."""

    async def execute(
        file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> str:
        content = await env.read_file(file_path)
        count = content.count(old_string)

        if count == 0:
            return f"Error: old_string not found in {file_path}"
        if count > 1 and not replace_all:
            return (
                f"Error: old_string found {count} times in {file_path}. "
                "Use replace_all=true to replace all occurrences, "
                "or provide more context to make the match unique."
            )

        if replace_all:
            new_content = content.replace(old_string, new_string)
            replaced = count
        else:
            new_content = content.replace(old_string, new_string, 1)
            replaced = 1

        await env.write_file(file_path, new_content)
        return f"Replaced {replaced} occurrence(s) in {file_path}"

    return ToolDefinition(
        name="edit_file",
        description="Edit a file by replacing exact string matches.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the file to edit"},
                "old_string": {"type": "string", "description": "The exact text to find and replace"},
                "new_string": {"type": "string", "description": "The replacement text"},
                "replace_all": {
                    "type": "boolean",
                    "description": "Replace all occurrences (default false)",
                    "default": False,
                },
            },
            "required": ["file_path", "old_string", "new_string"],
        },
        execute=execute,
    )


def make_shell_tool(env: ExecutionEnvironment, default_timeout_ms: int = 30000) -> ToolDefinition:
    """Create a shell tool bound to an environment."""

    async def execute(
        command: str, timeout_ms: int | None = None, description: str | None = None
    ) -> str:
        timeout = timeout_ms if timeout_ms is not None else default_timeout_ms
        result = await env.exec_command(command, timeout_ms=timeout)
        parts = []
        if result.stdout:
            parts.append(result.stdout)
        if result.stderr:
            parts.append(f"[stderr]\n{result.stderr}")
        if result.exit_code != 0:
            parts.append(f"[exit code: {result.exit_code}]")
        if result.timed_out:
            parts.append("[timed out]")
        output = "\n".join(parts) if parts else "(no output)"
        return truncate_output(output, "shell").text

    return ToolDefinition(
        name="shell",
        description="Execute a shell command and return stdout, stderr, and exit code.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute"},
                "timeout_ms": {
                    "type": "integer",
                    "description": f"Timeout in milliseconds (default {default_timeout_ms})",
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what this command does",
                },
            },
            "required": ["command"],
        },
        execute=execute,
    )


def make_grep_tool(env: ExecutionEnvironment) -> ToolDefinition:
    """Create a grep tool bound to an environment."""

    async def execute(
        pattern: str,
        path: str | None = None,
        glob_filter: str | None = None,
        case_insensitive: bool = False,
        max_results: int | None = None,
    ) -> str:
        search_path = path or "."
        kwargs: dict[str, object] = {}
        if glob_filter:
            kwargs["glob_filter"] = glob_filter
        if case_insensitive:
            kwargs["case_insensitive"] = True
        if max_results:
            kwargs["max_results"] = max_results

        result = await env.grep(pattern, search_path, **kwargs)
        return truncate_output(result, "grep").text

    return ToolDefinition(
        name="grep",
        description="Search file contents using regex patterns.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "File or directory to search (default '.')"},
                "glob_filter": {"type": "string", "description": "Glob pattern to filter files (e.g. '*.py')"},
                "case_insensitive": {"type": "boolean", "description": "Case-insensitive search", "default": False},
                "max_results": {"type": "integer", "description": "Maximum number of matches to return"},
            },
            "required": ["pattern"],
        },
        execute=execute,
    )


def make_glob_tool(env: ExecutionEnvironment) -> ToolDefinition:
    """Create a glob tool bound to an environment."""

    async def execute(pattern: str, path: str | None = None) -> str:
        search_path = path or "."
        matches = await env.glob(pattern, search_path)
        result = "\n".join(matches) if matches else "(no matches)"
        return truncate_output(result, "glob").text

    return ToolDefinition(
        name="glob",
        description="Find files matching a glob pattern, sorted by modification time.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob pattern (e.g. '**/*.py')"},
                "path": {"type": "string", "description": "Base directory to search from (default '.')"},
            },
            "required": ["pattern"],
        },
        execute=execute,
    )


def register_core_tools(
    env: ExecutionEnvironment,
    default_shell_timeout_ms: int = 30000,
) -> list[ToolDefinition]:
    """Create all core tool definitions bound to an environment."""
    return [
        make_read_file_tool(env),
        make_write_file_tool(env),
        make_edit_file_tool(env),
        make_shell_tool(env, default_timeout_ms=default_shell_timeout_ms),
        make_grep_tool(env),
        make_glob_tool(env),
    ]
