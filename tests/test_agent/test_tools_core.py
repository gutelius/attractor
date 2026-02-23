"""Tests for core tools."""

import pytest

from attractor_agent.environments.local import LocalExecutionEnvironment
from attractor_agent.tools.core import (
    make_read_file_tool,
    make_write_file_tool,
    make_edit_file_tool,
    make_shell_tool,
    make_grep_tool,
    make_glob_tool,
    register_core_tools,
)


@pytest.fixture
def env(tmp_path):
    return LocalExecutionEnvironment(working_dir=str(tmp_path))


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


class TestReadFile:
    async def test_basic_read(self, env, tmp_dir):
        (tmp_dir / "test.txt").write_text("hello\nworld\n")
        tool = make_read_file_tool(env)
        result = await tool.execute(file_path="test.txt")
        assert "hello" in result
        assert "world" in result

    async def test_line_numbers(self, env, tmp_dir):
        (tmp_dir / "test.txt").write_text("aaa\nbbb\nccc\n")
        tool = make_read_file_tool(env)
        result = await tool.execute(file_path="test.txt")
        assert "1\t" in result
        assert "2\t" in result

    async def test_offset_limit(self, env, tmp_dir):
        (tmp_dir / "test.txt").write_text("a\nb\nc\nd\ne\n")
        tool = make_read_file_tool(env)
        result = await tool.execute(file_path="test.txt", offset=2, limit=2)
        assert "b" in result
        assert "c" in result
        assert "a\n" not in result.split("\t")[0]  # line 'a' not first


class TestWriteFile:
    async def test_basic_write(self, env, tmp_dir):
        tool = make_write_file_tool(env)
        result = await tool.execute(file_path="out.txt", content="hello world")
        assert "Written" in result
        assert (tmp_dir / "out.txt").read_text() == "hello world"

    async def test_creates_parents(self, env, tmp_dir):
        tool = make_write_file_tool(env)
        await tool.execute(file_path="sub/dir/file.txt", content="nested")
        assert (tmp_dir / "sub" / "dir" / "file.txt").read_text() == "nested"


class TestEditFile:
    async def test_single_replace(self, env, tmp_dir):
        (tmp_dir / "code.py").write_text("def foo():\n    return 1\n")
        tool = make_edit_file_tool(env)
        result = await tool.execute(
            file_path="code.py", old_string="return 1", new_string="return 2"
        )
        assert "Replaced 1" in result
        assert (tmp_dir / "code.py").read_text() == "def foo():\n    return 2\n"

    async def test_not_found(self, env, tmp_dir):
        (tmp_dir / "code.py").write_text("hello")
        tool = make_edit_file_tool(env)
        result = await tool.execute(
            file_path="code.py", old_string="missing", new_string="x"
        )
        assert "Error" in result
        assert "not found" in result

    async def test_not_unique(self, env, tmp_dir):
        (tmp_dir / "code.py").write_text("x = 1\nx = 1\n")
        tool = make_edit_file_tool(env)
        result = await tool.execute(
            file_path="code.py", old_string="x = 1", new_string="x = 2"
        )
        assert "Error" in result
        assert "2 times" in result

    async def test_replace_all(self, env, tmp_dir):
        (tmp_dir / "code.py").write_text("x = 1\nx = 1\nx = 1\n")
        tool = make_edit_file_tool(env)
        result = await tool.execute(
            file_path="code.py",
            old_string="x = 1",
            new_string="x = 2",
            replace_all=True,
        )
        assert "Replaced 3" in result
        assert (tmp_dir / "code.py").read_text() == "x = 2\nx = 2\nx = 2\n"


class TestShell:
    async def test_basic_command(self, env):
        tool = make_shell_tool(env)
        result = await tool.execute(command="echo hello")
        assert "hello" in result

    async def test_exit_code(self, env):
        tool = make_shell_tool(env)
        result = await tool.execute(command="exit 1")
        assert "exit code: 1" in result

    async def test_timeout(self, env):
        tool = make_shell_tool(env)
        result = await tool.execute(command="sleep 10", timeout_ms=200)
        assert "timed out" in result

    async def test_stderr(self, env):
        tool = make_shell_tool(env)
        result = await tool.execute(command="echo err >&2")
        assert "err" in result


class TestGrep:
    async def test_basic_grep(self, env, tmp_dir):
        (tmp_dir / "data.txt").write_text("foo bar\nbaz qux\nfoo again\n")
        tool = make_grep_tool(env)
        result = await tool.execute(pattern="foo")
        assert "foo" in result

    async def test_no_matches(self, env, tmp_dir):
        (tmp_dir / "data.txt").write_text("hello world\n")
        tool = make_grep_tool(env)
        result = await tool.execute(pattern="zzzzz")
        # grep returns empty or no output for no matches
        assert "zzzzz" not in result


class TestGlob:
    async def test_basic_glob(self, env, tmp_dir):
        (tmp_dir / "a.py").write_text("")
        (tmp_dir / "b.txt").write_text("")
        (tmp_dir / "c.py").write_text("")
        tool = make_glob_tool(env)
        result = await tool.execute(pattern="*.py")
        assert "a.py" in result
        assert "c.py" in result
        assert "b.txt" not in result

    async def test_no_matches(self, env, tmp_dir):
        tool = make_glob_tool(env)
        result = await tool.execute(pattern="*.xyz")
        assert "no matches" in result


class TestRegisterCoreTools:
    def test_returns_six_tools(self, env):
        tools = register_core_tools(env)
        assert len(tools) == 6
        names = {t.name for t in tools}
        assert names == {"read_file", "write_file", "edit_file", "shell", "grep", "glob"}
