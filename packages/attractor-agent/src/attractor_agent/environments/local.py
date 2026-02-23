"""Local execution environment using subprocess and filesystem."""

from __future__ import annotations

import asyncio
import os
import platform
import signal
import time
from pathlib import Path

from attractor_agent.types import DirEntry, ExecResult


# Environment variables to always include
_SAFE_ENV_VARS = frozenset({
    "PATH", "HOME", "USER", "SHELL", "LANG", "TERM", "TMPDIR",
    "LC_ALL", "LC_CTYPE", "LOGNAME", "EDITOR", "VISUAL",
})

# Patterns to exclude from environment
_SECRET_PATTERNS = ("_API_KEY", "_SECRET", "_TOKEN", "_PASSWORD", "_CREDENTIAL")


def _filter_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    """Build a filtered environment dict, excluding secrets."""
    env: dict[str, str] = {}
    for key, val in os.environ.items():
        if key in _SAFE_ENV_VARS:
            env[key] = val
        elif not any(pat in key.upper() for pat in _SECRET_PATTERNS):
            env[key] = val
    if extra:
        env.update(extra)
    return env


class LocalExecutionEnvironment:
    """Execution environment backed by the local filesystem and subprocess."""

    def __init__(self, working_dir: str | None = None) -> None:
        self._working_dir = working_dir or os.getcwd()

    async def read_file(
        self, path: str, offset: int | None = None, limit: int | None = None
    ) -> str:
        full = self._resolve(path)
        text = Path(full).read_text()
        lines = text.splitlines(keepends=True)
        start = (offset or 1) - 1
        if limit is not None:
            lines = lines[start : start + limit]
        else:
            lines = lines[start:]
        return "".join(lines)

    async def write_file(self, path: str, content: str) -> None:
        full = self._resolve(path)
        Path(full).parent.mkdir(parents=True, exist_ok=True)
        Path(full).write_text(content)

    async def file_exists(self, path: str) -> bool:
        return Path(self._resolve(path)).exists()

    async def list_directory(self, path: str, depth: int = 1) -> list[DirEntry]:
        full = Path(self._resolve(path))
        entries: list[DirEntry] = []
        self._walk(full, entries, depth, 0)
        return entries

    def _walk(
        self, root: Path, entries: list[DirEntry], max_depth: int, current: int
    ) -> None:
        if current >= max_depth:
            return
        try:
            for item in sorted(root.iterdir(), key=lambda p: p.name):
                is_dir = item.is_dir()
                size = item.stat().st_size if not is_dir else None
                entries.append(DirEntry(name=item.name, is_dir=is_dir, size=size))
                if is_dir and current + 1 < max_depth:
                    self._walk(item, entries, max_depth, current + 1)
        except PermissionError:
            pass

    async def exec_command(
        self,
        command: str,
        timeout_ms: int = 30000,
        working_dir: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> ExecResult:
        cwd = self._resolve(working_dir) if working_dir else self._working_dir
        env = _filter_env(env_vars)
        timeout_s = timeout_ms / 1000.0
        start = time.monotonic()

        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )

        timed_out = False
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )
        except asyncio.TimeoutError:
            timed_out = True
            # SIGTERM first
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
            # Wait 2 seconds for graceful shutdown
            try:
                await asyncio.wait_for(proc.communicate(), timeout=2.0)
            except asyncio.TimeoutError:
                # SIGKILL
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
                try:
                    await proc.communicate()
                except Exception:
                    pass
            stdout = b""
            stderr = b"Command timed out"

        duration_ms = int((time.monotonic() - start) * 1000)
        return ExecResult(
            stdout=stdout.decode(errors="replace") if isinstance(stdout, bytes) else "",
            stderr=stderr.decode(errors="replace") if isinstance(stderr, bytes) else "",
            exit_code=proc.returncode or -1 if timed_out else (proc.returncode or 0),
            timed_out=timed_out,
            duration_ms=duration_ms,
        )

    async def grep(self, pattern: str, path: str, **options: object) -> str:
        args = ["grep", "-rn", pattern, self._resolve(path)]
        case_insensitive = options.get("case_insensitive", False)
        if case_insensitive:
            args.insert(1, "-i")
        glob_filter = options.get("glob_filter")
        if glob_filter:
            args.extend(["--include", str(glob_filter)])
        max_results = options.get("max_results")
        if max_results:
            args.extend(["-m", str(max_results)])
        result = await self.exec_command(" ".join(args))
        return result.stdout

    async def glob(self, pattern: str, path: str = ".") -> list[str]:
        import fnmatch

        root = Path(self._resolve(path))
        matches: list[str] = []
        if "**" in pattern:
            for p in root.rglob(pattern.replace("**/", "")):
                matches.append(str(p.relative_to(root)))
        else:
            for p in root.iterdir():
                if fnmatch.fnmatch(p.name, pattern):
                    matches.append(str(p.relative_to(root)))
        matches.sort(
            key=lambda m: Path(self._resolve(os.path.join(path, m))).stat().st_mtime,
            reverse=True,
        )
        return matches

    async def initialize(self) -> None:
        Path(self._working_dir).mkdir(parents=True, exist_ok=True)

    async def cleanup(self) -> None:
        pass

    def working_directory(self) -> str:
        return self._working_dir

    def platform(self) -> str:
        return platform.system().lower()

    def os_version(self) -> str:
        return platform.release()

    def _resolve(self, path: str) -> str:
        p = Path(path)
        if p.is_absolute():
            return str(p)
        return str(Path(self._working_dir) / p)
