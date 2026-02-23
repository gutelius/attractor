"""Tests for Context store."""

import threading

from attractor.context import Context


class TestBasicOps:
    def test_set_and_get(self):
        ctx = Context()
        ctx.set("key", "value")
        assert ctx.get("key") == "value"

    def test_get_default(self):
        ctx = Context()
        assert ctx.get("missing") is None
        assert ctx.get("missing", 42) == 42

    def test_get_string(self):
        ctx = Context()
        ctx.set("num", 123)
        assert ctx.get_string("num") == "123"

    def test_get_string_missing(self):
        ctx = Context()
        assert ctx.get_string("missing") == ""
        assert ctx.get_string("missing", "default") == "default"

    def test_init_with_values(self):
        ctx = Context(values={"a": 1, "b": 2})
        assert ctx.get("a") == 1
        assert ctx.get("b") == 2


class TestSnapshot:
    def test_snapshot_returns_copy(self):
        ctx = Context(values={"x": 10})
        snap = ctx.snapshot()
        assert snap == {"x": 10}
        snap["x"] = 999
        assert ctx.get("x") == 10  # original unchanged

    def test_snapshot_reflects_updates(self):
        ctx = Context()
        ctx.set("a", 1)
        assert ctx.snapshot() == {"a": 1}
        ctx.set("b", 2)
        assert ctx.snapshot() == {"a": 1, "b": 2}


class TestClone:
    def test_clone_is_independent(self):
        ctx = Context(values={"x": [1, 2, 3]})
        ctx.append_log("entry1")
        clone = ctx.clone()
        assert clone.get("x") == [1, 2, 3]
        assert clone.logs == ["entry1"]

        # Mutate clone - original unaffected
        clone.set("x", "changed")
        clone.append_log("entry2")
        assert ctx.get("x") == [1, 2, 3]
        assert len(ctx.logs) == 1

    def test_deep_copy_nested_values(self):
        ctx = Context(values={"nested": {"a": [1, 2]}})
        clone = ctx.clone()
        clone.get("nested")["a"].append(3)
        assert ctx.get("nested")["a"] == [1, 2]  # original unchanged


class TestApplyUpdates:
    def test_apply_updates(self):
        ctx = Context(values={"a": 1})
        ctx.apply_updates({"b": 2, "c": 3})
        assert ctx.get("a") == 1
        assert ctx.get("b") == 2
        assert ctx.get("c") == 3

    def test_apply_updates_overwrites(self):
        ctx = Context(values={"a": 1})
        ctx.apply_updates({"a": 99})
        assert ctx.get("a") == 99


class TestAppendLog:
    def test_append_log(self):
        ctx = Context()
        ctx.append_log("step 1")
        ctx.append_log("step 2")
        assert ctx.logs == ["step 1", "step 2"]

    def test_logs_returns_copy(self):
        ctx = Context()
        ctx.append_log("entry")
        logs = ctx.logs
        logs.append("extra")
        assert len(ctx.logs) == 1


class TestThreadSafety:
    def test_concurrent_writes(self):
        ctx = Context()
        errors = []

        def writer(prefix: str, count: int):
            try:
                for i in range(count):
                    ctx.set(f"{prefix}_{i}", i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(f"t{t}", 100)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(ctx.snapshot()) == 400

    def test_concurrent_reads_and_writes(self):
        ctx = Context(values={f"k{i}": i for i in range(100)})
        errors = []

        def reader():
            try:
                for _ in range(100):
                    ctx.snapshot()
                    ctx.get("k50")
            except Exception as e:
                errors.append(e)

        def writer():
            try:
                for i in range(100):
                    ctx.set(f"new_{i}", i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(3)]
        threads.append(threading.Thread(target=writer))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
