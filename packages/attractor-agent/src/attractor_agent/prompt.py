"""System prompt construction with 5-layer assembly."""

from __future__ import annotations

import os
from pathlib import Path

# Provider-specific instruction file mappings
_PROVIDER_FILES: dict[str, set[str]] = {
    "openai": {"AGENTS.md", ".codex/instructions.md"},
    "anthropic": {"AGENTS.md", "CLAUDE.md"},
    "gemini": {"AGENTS.md", "GEMINI.md"},
}

# Universal files loaded for any provider
_UNIVERSAL_FILES = {"AGENTS.md"}

MAX_PROJECT_DOCS_BYTES = 32 * 1024  # 32KB budget


def build_environment_context(
    working_dir: str,
    platform_name: str,
    os_version: str,
    git_branch: str | None = None,
    git_status: str | None = None,
    git_recent_commits: list[str] | None = None,
    model_name: str | None = None,
    date: str | None = None,
) -> str:
    """Build the environment context block (Layer 2)."""
    is_git = git_branch is not None
    lines = [
        "<environment>",
        f"Working directory: {working_dir}",
        f"Is git repository: {str(is_git).lower()}",
    ]
    if git_branch:
        lines.append(f"Git branch: {git_branch}")
    lines.extend([
        f"Platform: {platform_name}",
        f"OS version: {os_version}",
    ])
    if date:
        lines.append(f"Today's date: {date}")
    if model_name:
        lines.append(f"Model: {model_name}")
    lines.append("</environment>")

    if git_status:
        lines.append(f"\nGit status:\n{git_status}")
    if git_recent_commits:
        lines.append("\nRecent commits:")
        for commit in git_recent_commits[:10]:
            lines.append(f"  {commit}")

    return "\n".join(lines)


def discover_project_docs(
    working_dir: str,
    provider_id: str,
    git_root: str | None = None,
) -> list[str]:
    """Discover project instruction files from git root to working dir (Layer 4).

    Walks from git_root (or working_dir if not in git) to working_dir,
    collecting provider-appropriate instruction files.
    """
    allowed_files = _PROVIDER_FILES.get(provider_id, _UNIVERSAL_FILES)
    root = Path(git_root) if git_root else Path(working_dir)
    cwd = Path(working_dir)

    # Build the path from root to cwd
    dirs_to_check: list[Path] = [root]
    try:
        relative = cwd.relative_to(root)
        parts = relative.parts
        current = root
        for part in parts:
            current = current / part
            if current != root:
                dirs_to_check.append(current)
    except ValueError:
        # cwd is not under root
        dirs_to_check = [cwd]

    docs: list[str] = []
    total_bytes = 0

    for directory in dirs_to_check:
        for filename in sorted(allowed_files):
            filepath = directory / filename
            if filepath.is_file():
                try:
                    content = filepath.read_text()
                    if total_bytes + len(content.encode()) > MAX_PROJECT_DOCS_BYTES:
                        remaining = MAX_PROJECT_DOCS_BYTES - total_bytes
                        if remaining > 0:
                            docs.append(content[:remaining])
                            docs.append("[Project instructions truncated at 32KB]")
                        return docs
                    docs.append(f"# {filepath.relative_to(root)}\n\n{content}")
                    total_bytes += len(content.encode())
                except (OSError, UnicodeDecodeError):
                    pass

    return docs


def build_system_prompt(
    base_instructions: str,
    environment_context: str | None = None,
    tool_descriptions: list[tuple[str, str]] | None = None,
    project_docs: list[str] | None = None,
    user_instructions: str | None = None,
) -> str:
    """Assemble the 5-layer system prompt.

    Layers (in order, later layers take precedence):
        1. Provider-specific base instructions
        2. Environment context (platform, git, working dir, date, model)
        3. Tool descriptions
        4. Project-specific instructions (AGENTS.md, CLAUDE.md, etc.)
        5. User instructions override
    """
    layers: list[str] = []

    # Layer 1: Base instructions
    layers.append(base_instructions)

    # Layer 2: Environment context
    if environment_context:
        layers.append(environment_context)

    # Layer 3: Tool descriptions
    if tool_descriptions:
        tool_block = "# Available Tools\n"
        for name, desc in tool_descriptions:
            tool_block += f"\n## {name}\n{desc}\n"
        layers.append(tool_block)

    # Layer 4: Project docs
    if project_docs:
        layers.append("# Project Instructions\n\n" + "\n\n".join(project_docs))

    # Layer 5: User instructions
    if user_instructions:
        layers.append(f"# User Instructions\n\n{user_instructions}")

    return "\n\n".join(layers)
