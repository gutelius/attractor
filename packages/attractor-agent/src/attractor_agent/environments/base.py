"""Execution environment protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from attractor_agent.types import DirEntry, ExecResult


@runtime_checkable
class ExecutionEnvironment(Protocol):
    """Interface for all execution environments."""

    async def read_file(
        self, path: str, offset: int | None = None, limit: int | None = None
    ) -> str: ...

    async def write_file(self, path: str, content: str) -> None: ...

    async def file_exists(self, path: str) -> bool: ...

    async def list_directory(self, path: str, depth: int = 1) -> list[DirEntry]: ...

    async def exec_command(
        self,
        command: str,
        timeout_ms: int = 30000,
        working_dir: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> ExecResult: ...

    async def grep(
        self, pattern: str, path: str, **options: object
    ) -> str: ...

    async def glob(self, pattern: str, path: str = ".") -> list[str]: ...

    async def initialize(self) -> None: ...

    async def cleanup(self) -> None: ...

    def working_directory(self) -> str: ...

    def platform(self) -> str: ...

    def os_version(self) -> str: ...
