"""Tests for execution environments."""

import os
import platform

import pytest

from attractor_agent.environments.base import ExecutionEnvironment
from attractor_agent.environments.local import LocalExecutionEnvironment, _filter_env
from attractor_agent.types import DirEntry, ExecResult


@pytest.fixture
def tmp_env(tmp_path):
    """Create a LocalExecutionEnvironment with a temp working dir."""
    return LocalExecutionEnvironment(working_dir=str(tmp_path))


class TestLocalExecutionEnvironment:
    """Tests for LocalExecutionEnvironment."""

    def test_implements_protocol(self, tmp_env):
        assert isinstance(tmp_env, ExecutionEnvironment)

    async def test_read_write_file(self, tmp_env, tmp_path):
        await tmp_env.write_file("hello.txt", "line1\nline2\nline3\n")
        content = await tmp_env.read_file("hello.txt")
        assert content == "line1\nline2\nline3\n"

    async def test_read_file_with_offset_limit(self, tmp_env, tmp_path):
        await tmp_env.write_file("data.txt", "a\nb\nc\nd\ne\n")
        content = await tmp_env.read_file("data.txt", offset=2, limit=2)
        assert content == "b\nc\n"

    async def test_write_file_creates_parents(self, tmp_env, tmp_path):
        await tmp_env.write_file("sub/dir/file.txt", "nested")
        assert (tmp_path / "sub" / "dir" / "file.txt").read_text() == "nested"

    async def test_file_exists(self, tmp_env, tmp_path):
        assert not await tmp_env.file_exists("nope.txt")
        await tmp_env.write_file("yes.txt", "hi")
        assert await tmp_env.file_exists("yes.txt")

    async def test_list_directory(self, tmp_env, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "subdir").mkdir()
        entries = await tmp_env.list_directory(".")
        names = {e.name for e in entries}
        assert "a.txt" in names
        assert "subdir" in names
        dirs = {e.name for e in entries if e.is_dir}
        assert "subdir" in dirs

    async def test_list_directory_depth(self, tmp_env, tmp_path):
        (tmp_path / "d").mkdir()
        (tmp_path / "d" / "inner.txt").write_text("x")
        shallow = await tmp_env.list_directory(".", depth=1)
        deep = await tmp_env.list_directory(".", depth=2)
        shallow_names = {e.name for e in shallow}
        deep_names = {e.name for e in deep}
        assert "inner.txt" not in shallow_names
        assert "inner.txt" in deep_names

    async def test_exec_command_basic(self, tmp_env):
        result = await tmp_env.exec_command("echo hello")
        assert result.stdout.strip() == "hello"
        assert result.exit_code == 0
        assert not result.timed_out
        assert result.duration_ms >= 0

    async def test_exec_command_exit_code(self, tmp_env):
        result = await tmp_env.exec_command("exit 42")
        assert result.exit_code == 42

    async def test_exec_command_stderr(self, tmp_env):
        result = await tmp_env.exec_command("echo err >&2")
        assert "err" in result.stderr

    async def test_exec_command_timeout(self, tmp_env):
        result = await tmp_env.exec_command("sleep 10", timeout_ms=200)
        assert result.timed_out

    async def test_exec_command_working_dir(self, tmp_env, tmp_path):
        sub = tmp_path / "mydir"
        sub.mkdir()
        result = await tmp_env.exec_command("pwd", working_dir=str(sub))
        assert str(sub) in result.stdout

    async def test_exec_command_env_vars(self, tmp_env):
        result = await tmp_env.exec_command(
            "echo $MY_CUSTOM_VAR", env_vars={"MY_CUSTOM_VAR": "hello123"}
        )
        assert "hello123" in result.stdout

    async def test_grep(self, tmp_env, tmp_path):
        (tmp_path / "search.txt").write_text("foo bar\nbaz qux\nfoo again\n")
        output = await tmp_env.grep("foo", ".")
        assert "foo" in output

    async def test_glob(self, tmp_env, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.txt").write_text("")
        (tmp_path / "c.py").write_text("")
        matches = await tmp_env.glob("*.py")
        assert len(matches) == 2
        assert all(m.endswith(".py") for m in matches)

    def test_working_directory(self, tmp_env, tmp_path):
        assert tmp_env.working_directory() == str(tmp_path)

    def test_platform(self, tmp_env):
        assert tmp_env.platform() == platform.system().lower()

    def test_os_version(self, tmp_env):
        assert tmp_env.os_version() == platform.release()

    async def test_initialize(self, tmp_path):
        new_dir = str(tmp_path / "new_workdir")
        env = LocalExecutionEnvironment(working_dir=new_dir)
        await env.initialize()
        assert os.path.isdir(new_dir)


class TestEnvFiltering:
    """Tests for environment variable filtering."""

    def test_safe_vars_included(self):
        env = _filter_env()
        # PATH should always be present
        assert "PATH" in env

    def test_secrets_excluded(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
        monkeypatch.setenv("DB_PASSWORD", "pass123")
        monkeypatch.setenv("AUTH_TOKEN", "tok")
        monkeypatch.setenv("MY_SECRET", "shhh")
        monkeypatch.setenv("AWS_CREDENTIAL", "cred")
        env = _filter_env()
        assert "OPENAI_API_KEY" not in env
        assert "DB_PASSWORD" not in env
        assert "AUTH_TOKEN" not in env
        assert "MY_SECRET" not in env
        assert "AWS_CREDENTIAL" not in env

    def test_extra_vars_override(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
        env = _filter_env(extra={"CUSTOM": "val", "OPENAI_API_KEY": "override"})
        assert env["CUSTOM"] == "val"
        # Extra vars override the filtering
        assert env["OPENAI_API_KEY"] == "override"

    def test_normal_vars_pass_through(self, monkeypatch):
        monkeypatch.setenv("MY_APP_CONFIG", "value123")
        env = _filter_env()
        assert env.get("MY_APP_CONFIG") == "value123"
