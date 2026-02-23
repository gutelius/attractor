"""Core types for the agent package."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ExecResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    timed_out: bool = False
    duration_ms: int = 0


@dataclass
class DirEntry:
    name: str = ""
    is_dir: bool = False
    size: int | None = None
