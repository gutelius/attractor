"""Tests for apply_patch v4a format."""

import pytest

from attractor_agent.environments.local import LocalExecutionEnvironment
from attractor_agent.tools.patch import parse_patch, apply_hunk, apply_patch, Hunk


@pytest.fixture
def env(tmp_path):
    return LocalExecutionEnvironment(working_dir=str(tmp_path))


class TestParsePatch:
    def test_add_file(self):
        patch = """\
*** Begin Patch
*** Add File: src/utils/helpers.py
+def greet(name):
+    return f"Hello, {name}!"
*** End Patch"""
        ops = parse_patch(patch)
        assert len(ops) == 1
        assert ops[0].kind == "add"
        assert ops[0].path == "src/utils/helpers.py"
        assert ops[0].added_lines == ['def greet(name):', '    return f"Hello, {name}!"']

    def test_delete_file(self):
        patch = """\
*** Begin Patch
*** Delete File: src/old_module.py
*** End Patch"""
        ops = parse_patch(patch)
        assert len(ops) == 1
        assert ops[0].kind == "delete"
        assert ops[0].path == "src/old_module.py"

    def test_update_file(self):
        patch = """\
*** Begin Patch
*** Update File: src/main.py
@@ def main():
     print("Hello")
-    return 0
+    print("World")
+    return 1
*** End Patch"""
        ops = parse_patch(patch)
        assert len(ops) == 1
        op = ops[0]
        assert op.kind == "update"
        assert op.path == "src/main.py"
        assert len(op.hunks) == 1
        assert op.hunks[0].context_hint == "def main():"

    def test_update_with_rename(self):
        patch = """\
*** Begin Patch
*** Update File: old_name.py
*** Move to: new_name.py
@@ import os
 import sys
-import old_dep
+import new_dep
*** End Patch"""
        ops = parse_patch(patch)
        assert len(ops) == 1
        assert ops[0].move_to == "new_name.py"

    def test_multi_hunk(self):
        patch = """\
*** Begin Patch
*** Update File: src/config.py
@@ DEFAULT_TIMEOUT = 30
-DEFAULT_TIMEOUT = 30
+DEFAULT_TIMEOUT = 60
@@ def load_config():
     config = {}
-    config["debug"] = False
+    config["debug"] = True
*** End Patch"""
        ops = parse_patch(patch)
        assert len(ops) == 1
        assert len(ops[0].hunks) == 2

    def test_multiple_operations(self):
        patch = """\
*** Begin Patch
*** Add File: new.py
+# new file
*** Delete File: old.py
*** Update File: existing.py
@@ line
 context
-old
+new
*** End Patch"""
        ops = parse_patch(patch)
        assert len(ops) == 3
        assert ops[0].kind == "add"
        assert ops[1].kind == "delete"
        assert ops[2].kind == "update"


class TestApplyHunk:
    def test_simple_replacement(self):
        file_lines = ["def main():", '    print("Hello")', "    return 0"]
        hunk = Hunk(
            context_hint="def main():",
            lines=[
                (" ", "def main():"),
                (" ", '    print("Hello")'),
                ("-", "    return 0"),
                ("+", '    print("World")'),
                ("+", "    return 1"),
            ],
        )
        result = apply_hunk(file_lines, hunk)
        assert result == ["def main():", '    print("Hello")', '    print("World")', "    return 1"]

    def test_add_only(self):
        file_lines = ["line1", "line2"]
        hunk = Hunk(
            context_hint="line1",
            lines=[
                (" ", "line1"),
                ("+", "inserted"),
                (" ", "line2"),
            ],
        )
        result = apply_hunk(file_lines, hunk)
        assert result == ["line1", "inserted", "line2"]

    def test_delete_only(self):
        file_lines = ["keep", "remove", "keep2"]
        hunk = Hunk(
            context_hint="keep",
            lines=[
                (" ", "keep"),
                ("-", "remove"),
                (" ", "keep2"),
            ],
        )
        result = apply_hunk(file_lines, hunk)
        assert result == ["keep", "keep2"]


class TestApplyPatchIntegration:
    async def test_add_file(self, env, tmp_path):
        patch = """\
*** Begin Patch
*** Add File: greet.py
+def greet(name):
+    return f"Hello, {name}!"
*** End Patch"""
        result = await apply_patch(env, patch)
        assert "Added" in result
        content = (tmp_path / "greet.py").read_text()
        assert "def greet" in content

    async def test_delete_file(self, env, tmp_path):
        (tmp_path / "doomed.py").write_text("old stuff")
        patch = """\
*** Begin Patch
*** Delete File: doomed.py
*** End Patch"""
        result = await apply_patch(env, patch)
        assert "Deleted" in result
        assert not (tmp_path / "doomed.py").exists()

    async def test_update_file(self, env, tmp_path):
        (tmp_path / "main.py").write_text('def main():\n    print("Hello")\n    return 0\n')
        patch = """\
*** Begin Patch
*** Update File: main.py
@@ def main():
     print("Hello")
-    return 0
+    return 1
*** End Patch"""
        result = await apply_patch(env, patch)
        assert "Updated" in result
        content = (tmp_path / "main.py").read_text()
        assert "return 1" in content
        assert "return 0" not in content

    async def test_rename_file(self, env, tmp_path):
        (tmp_path / "old.py").write_text("import os\nimport sys\nimport old_dep\n")
        patch = """\
*** Begin Patch
*** Update File: old.py
*** Move to: new.py
@@ import os
 import sys
-import old_dep
+import new_dep
*** End Patch"""
        result = await apply_patch(env, patch)
        assert "moved" in result.lower() or "Move" in result
        assert (tmp_path / "new.py").exists()
        content = (tmp_path / "new.py").read_text()
        assert "import new_dep" in content

    async def test_fuzzy_matching(self, env, tmp_path):
        # Extra whitespace in file vs patch
        (tmp_path / "fuzzy.py").write_text("x  =  1\ny = 2\n")
        patch = """\
*** Begin Patch
*** Update File: fuzzy.py
@@ x = 1
 x  =  1
-y = 2
+y = 3
*** End Patch"""
        result = await apply_patch(env, patch)
        assert "Updated" in result
        content = (tmp_path / "fuzzy.py").read_text()
        assert "y = 3" in content
