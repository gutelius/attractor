"""Output truncation for tool results."""

from __future__ import annotations

from dataclasses import dataclass


# Character limits per tool
CHAR_LIMITS: dict[str, int] = {
    "read_file": 50_000,
    "shell": 30_000,
    "grep": 20_000,
    "glob": 20_000,
    "edit_file": 10_000,
    "apply_patch": 10_000,
    "write_file": 1_000,
    "spawn_agent": 20_000,
}

# Line limits per tool
LINE_LIMITS: dict[str, int] = {
    "shell": 256,
    "grep": 200,
    "glob": 500,
}

DEFAULT_CHAR_LIMIT = 30_000
DEFAULT_LINE_LIMIT = 500


@dataclass
class TruncationResult:
    text: str
    was_truncated: bool
    original_chars: int
    original_lines: int


def truncate_chars(text: str, limit: int, mode: str = "head_tail") -> str:
    """Truncate text by character count.

    Modes:
        head_tail: Keep first and last portions with truncation notice.
        tail: Keep only the last portion.
    """
    if len(text) <= limit:
        return text

    if mode == "tail":
        return f"... [truncated {len(text) - limit} chars] ...\n" + text[-limit:]

    # head_tail: split evenly
    head_size = limit // 2
    tail_size = limit - head_size
    removed = len(text) - limit
    return (
        text[:head_size]
        + f"\n... [truncated {removed} chars] ...\n"
        + text[-tail_size:]
    )


def truncate_lines(text: str, limit: int) -> str:
    """Truncate text by line count, keeping head and tail."""
    lines = text.splitlines(keepends=True)
    if len(lines) <= limit:
        return text

    head_count = limit // 2
    tail_count = limit - head_count
    removed = len(lines) - limit
    head = "".join(lines[:head_count])
    tail = "".join(lines[-tail_count:])
    return head + f"\n... [truncated {removed} lines] ...\n" + tail


def truncate_output(
    text: str,
    tool_name: str,
    char_limit: int | None = None,
    line_limit: int | None = None,
    char_mode: str = "head_tail",
) -> TruncationResult:
    """Truncate tool output, applying character limits first, then line limits.

    Args:
        text: The text to truncate.
        tool_name: Tool name for looking up default limits.
        char_limit: Override character limit.
        line_limit: Override line limit.
        char_mode: Character truncation mode ('head_tail' or 'tail').
    """
    original_chars = len(text)
    original_lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)

    max_chars = char_limit if char_limit is not None else CHAR_LIMITS.get(tool_name, DEFAULT_CHAR_LIMIT)
    max_lines = line_limit if line_limit is not None else LINE_LIMITS.get(tool_name, DEFAULT_LINE_LIMIT)

    result = text
    was_truncated = False

    # Character truncation first
    if len(result) > max_chars:
        result = truncate_chars(result, max_chars, mode=char_mode)
        was_truncated = True

    # Then line truncation
    line_count = result.count("\n") + (1 if result and not result.endswith("\n") else 0)
    if line_count > max_lines:
        result = truncate_lines(result, max_lines)
        was_truncated = True

    return TruncationResult(
        text=result,
        was_truncated=was_truncated,
        original_chars=original_chars,
        original_lines=original_lines,
    )
