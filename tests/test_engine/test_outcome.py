"""Tests for Outcome and StageStatus."""

from attractor.outcome import Outcome, StageStatus


class TestStageStatus:
    def test_values(self):
        assert StageStatus.SUCCESS.value == "success"
        assert StageStatus.FAIL.value == "fail"
        assert StageStatus.PARTIAL_SUCCESS.value == "partial_success"
        assert StageStatus.RETRY.value == "retry"
        assert StageStatus.SKIPPED.value == "skipped"

    def test_from_value(self):
        assert StageStatus("success") == StageStatus.SUCCESS
        assert StageStatus("fail") == StageStatus.FAIL


class TestOutcome:
    def test_defaults(self):
        o = Outcome()
        assert o.status == StageStatus.SUCCESS
        assert o.preferred_label == ""
        assert o.suggested_next_ids == []
        assert o.context_updates == {}
        assert o.notes == ""
        assert o.failure_reason == ""

    def test_is_success(self):
        assert Outcome(status=StageStatus.SUCCESS).is_success
        assert Outcome(status=StageStatus.PARTIAL_SUCCESS).is_success
        assert not Outcome(status=StageStatus.FAIL).is_success
        assert not Outcome(status=StageStatus.RETRY).is_success
        assert not Outcome(status=StageStatus.SKIPPED).is_success

    def test_is_failure(self):
        assert Outcome(status=StageStatus.FAIL).is_failure
        assert not Outcome(status=StageStatus.SUCCESS).is_failure
        assert not Outcome(status=StageStatus.RETRY).is_failure

    def test_is_retry(self):
        assert Outcome(status=StageStatus.RETRY).is_retry
        assert not Outcome(status=StageStatus.SUCCESS).is_retry

    def test_with_context_updates(self):
        o = Outcome(
            status=StageStatus.SUCCESS,
            context_updates={"result": "42", "done": True},
        )
        assert o.context_updates["result"] == "42"

    def test_with_preferred_label(self):
        o = Outcome(status=StageStatus.SUCCESS, preferred_label="approved")
        assert o.preferred_label == "approved"

    def test_with_suggested_next(self):
        o = Outcome(status=StageStatus.SUCCESS, suggested_next_ids=["NodeA", "NodeB"])
        assert o.suggested_next_ids == ["NodeA", "NodeB"]

    def test_failure_with_reason(self):
        o = Outcome(status=StageStatus.FAIL, failure_reason="timeout exceeded")
        assert o.is_failure
        assert o.failure_reason == "timeout exceeded"
