"""apply_patch v4a format parser and applier."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from attractor_agent.environments.base import ExecutionEnvironment
from attractor_llm.types import ToolDefinition


@dataclass
class Hunk:
    context_hint: str = ""
    lines: list[tuple[str, str]] = field(default_factory=list)  # (prefix, content)


@dataclass
class PatchOp:
    kind: Literal["add", "delete", "update"]
    path: str
    move_to: str | None = None
    added_lines: list[str] = field(default_factory=list)
    hunks: list[Hunk] = field(default_factory=list)


def parse_patch(text: str) -> list[PatchOp]:
    """Parse a v4a patch string into operations."""
    lines = text.splitlines()
    ops: list[PatchOp] = []

    i = 0
    # Find "*** Begin Patch"
    while i < len(lines) and lines[i].strip() != "*** Begin Patch":
        i += 1
    i += 1  # skip Begin Patch

    while i < len(lines):
        line = lines[i]
        if line.strip() == "*** End Patch":
            break

        if line.startswith("*** Add File: "):
            path = line[len("*** Add File: "):].strip()
            i += 1
            added: list[str] = []
            while i < len(lines) and not lines[i].startswith("***") and not lines[i].startswith("@@"):
                if lines[i].startswith("+"):
                    added.append(lines[i][1:])
                i += 1
            ops.append(PatchOp(kind="add", path=path, added_lines=added))

        elif line.startswith("*** Delete File: "):
            path = line[len("*** Delete File: "):].strip()
            i += 1
            ops.append(PatchOp(kind="delete", path=path))

        elif line.startswith("*** Update File: "):
            path = line[len("*** Update File: "):].strip()
            i += 1
            move_to = None
            if i < len(lines) and lines[i].startswith("*** Move to: "):
                move_to = lines[i][len("*** Move to: "):].strip()
                i += 1
            hunks: list[Hunk] = []
            while i < len(lines) and not lines[i].startswith("***"):
                if lines[i].startswith("@@ "):
                    hint = lines[i][3:].strip()
                    i += 1
                    hunk_lines: list[tuple[str, str]] = []
                    while i < len(lines) and not lines[i].startswith("@@") and not lines[i].startswith("***"):
                        raw = lines[i]
                        if raw and raw[0] in (" ", "-", "+"):
                            hunk_lines.append((raw[0], raw[1:]))
                        i += 1
                    hunks.append(Hunk(context_hint=hint, lines=hunk_lines))
                else:
                    i += 1
            ops.append(PatchOp(kind="update", path=path, move_to=move_to, hunks=hunks))
        else:
            i += 1

    return ops


def _find_hunk_position(file_lines: list[str], hunk: Hunk) -> int:
    """Find where a hunk should be applied in the file.

    Returns the index in file_lines where the hunk's context starts.
    """
    # Build the sequence of context and delete lines (what should exist in file)
    existing = [(prefix, content) for prefix, content in hunk.lines if prefix in (" ", "-")]
    if not existing:
        return 0

    # Try exact match
    pos = _match_lines(file_lines, existing)
    if pos >= 0:
        return pos

    # Try fuzzy match (whitespace normalized)
    pos = _fuzzy_match(file_lines, existing)
    if pos >= 0:
        return pos

    # Use context hint
    if hunk.context_hint:
        for idx, fl in enumerate(file_lines):
            if hunk.context_hint.strip() in fl.strip():
                return idx

    return 0


def _match_lines(file_lines: list[str], existing: list[tuple[str, str]]) -> int:
    """Exact match of context/delete lines in file."""
    n = len(existing)
    for start in range(len(file_lines) - n + 1):
        match = True
        for j, (prefix, content) in enumerate(existing):
            if file_lines[start + j] != content:
                match = False
                break
        if match:
            return start
    return -1


def _fuzzy_match(file_lines: list[str], existing: list[tuple[str, str]]) -> int:
    """Fuzzy match with whitespace normalization."""
    n = len(existing)
    for start in range(len(file_lines) - n + 1):
        match = True
        for j, (prefix, content) in enumerate(existing):
            if _normalize(file_lines[start + j]) != _normalize(content):
                match = False
                break
        if match:
            return start
    return -1


def _normalize(s: str) -> str:
    """Normalize whitespace for fuzzy matching."""
    return re.sub(r"\s+", " ", s.strip())


def apply_hunk(file_lines: list[str], hunk: Hunk) -> list[str]:
    """Apply a single hunk to file lines, returning new lines."""
    pos = _find_hunk_position(file_lines, hunk)
    result = list(file_lines[:pos])

    # Count how many existing lines the hunk covers
    existing_count = sum(1 for p, _ in hunk.lines if p in (" ", "-"))

    for prefix, content in hunk.lines:
        if prefix == " ":
            result.append(content)
        elif prefix == "+":
            result.append(content)
        # "-" lines are skipped (deleted)

    # Append remaining file lines after the hunk's range
    result.extend(file_lines[pos + existing_count:])
    return result


async def apply_patch(env: ExecutionEnvironment, patch_text: str) -> str:
    """Apply a v4a patch to the environment's filesystem."""
    ops = parse_patch(patch_text)
    results: list[str] = []

    for op in ops:
        if op.kind == "add":
            content = "\n".join(op.added_lines)
            if op.added_lines:
                content += "\n"
            await env.write_file(op.path, content)
            results.append(f"Added {op.path}")

        elif op.kind == "delete":
            # Write empty to signal deletion; real impl would use os.remove
            result = await env.exec_command(f"rm -f {op.path}")
            results.append(f"Deleted {op.path}")

        elif op.kind == "update":
            content = await env.read_file(op.path)
            file_lines = content.splitlines()

            for hunk in op.hunks:
                file_lines = apply_hunk(file_lines, hunk)

            new_content = "\n".join(file_lines)
            if file_lines:
                new_content += "\n"

            target_path = op.move_to or op.path
            await env.write_file(target_path, new_content)

            if op.move_to and op.move_to != op.path:
                await env.exec_command(f"rm -f {op.path}")
                results.append(f"Updated and moved {op.path} → {op.move_to}")
            else:
                results.append(f"Updated {op.path}")

    return "\n".join(results) if results else "No operations in patch"


def make_apply_patch_tool(env: ExecutionEnvironment) -> ToolDefinition:
    """Create an apply_patch tool bound to an environment."""

    async def execute(patch: str) -> str:
        return await apply_patch(env, patch)

    return ToolDefinition(
        name="apply_patch",
        description="Apply a patch in v4a format to create, delete, or update files.",
        parameters={
            "type": "object",
            "properties": {
                "patch": {
                    "type": "string",
                    "description": "The patch content in v4a format",
                },
            },
            "required": ["patch"],
        },
        execute=execute,
    )
