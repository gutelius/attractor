"""Tests for condition expression evaluator."""

from attractor.conditions import evaluate_condition, resolve_key
from attractor.context import Context
from attractor.outcome import Outcome, StageStatus


def _ctx(**kw) -> Context:
    return Context(values=kw)


def _outcome(status="success", preferred_label="") -> Outcome:
    return Outcome(status=StageStatus(status), preferred_label=preferred_label)


class TestResolveKey:
    def test_outcome_key(self):
        assert resolve_key("outcome", _outcome("success"), _ctx()) == "success"
        assert resolve_key("outcome", _outcome("fail"), _ctx()) == "fail"

    def test_preferred_label_key(self):
        assert resolve_key("preferred_label", _outcome(preferred_label="approved"), _ctx()) == "approved"

    def test_context_dotted_key(self):
        assert resolve_key("context.ready", _outcome(), _ctx(ready="true")) == "true"

    def test_context_dotted_missing(self):
        assert resolve_key("context.missing", _outcome(), _ctx()) == ""

    def test_bare_context_key(self):
        assert resolve_key("tests_passed", _outcome(), _ctx(tests_passed="true")) == "true"

    def test_bare_missing(self):
        assert resolve_key("nope", _outcome(), _ctx()) == ""


class TestEvaluateCondition:
    def test_empty_condition(self):
        assert evaluate_condition("", _outcome(), _ctx()) is True
        assert evaluate_condition("  ", _outcome(), _ctx()) is True

    def test_simple_equality(self):
        assert evaluate_condition("outcome=success", _outcome("success"), _ctx()) is True
        assert evaluate_condition("outcome=success", _outcome("fail"), _ctx()) is False

    def test_inequality(self):
        assert evaluate_condition("outcome!=fail", _outcome("success"), _ctx()) is True
        assert evaluate_condition("outcome!=fail", _outcome("fail"), _ctx()) is False

    def test_and_clauses(self):
        ctx = _ctx(tests_passed="true")
        assert evaluate_condition("outcome=success&&context.tests_passed=true", _outcome("success"), ctx) is True
        assert evaluate_condition("outcome=success&&context.tests_passed=true", _outcome("fail"), ctx) is False

    def test_context_key_lookup(self):
        ctx = _ctx(loop_state="running")
        assert evaluate_condition("context.loop_state!=exhausted", _outcome(), ctx) is True
        ctx2 = _ctx(loop_state="exhausted")
        assert evaluate_condition("context.loop_state!=exhausted", _outcome(), ctx2) is False

    def test_preferred_label(self):
        o = _outcome(preferred_label="Fix")
        assert evaluate_condition("preferred_label=Fix", o, _ctx()) is True
        assert evaluate_condition("preferred_label=Approve", o, _ctx()) is False

    def test_bare_key_truthy(self):
        assert evaluate_condition("tests_passed", _outcome(), _ctx(tests_passed="yes")) is True
        assert evaluate_condition("tests_passed", _outcome(), _ctx()) is False

    def test_missing_context_equals_empty(self):
        assert evaluate_condition("context.missing=", _outcome(), _ctx()) is True
        assert evaluate_condition("context.missing=something", _outcome(), _ctx()) is False

    def test_whitespace_handling(self):
        assert evaluate_condition("outcome = success", _outcome("success"), _ctx()) is True
        assert evaluate_condition(" outcome=success && context.x=1 ", _outcome("success"), _ctx(x="1")) is True
