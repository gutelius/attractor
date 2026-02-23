"""Condition expression evaluator for edge routing."""

from __future__ import annotations

from typing import Any

from attractor.context import Context
from attractor.outcome import Outcome


def resolve_key(key: str, outcome: Outcome, context: Context) -> str:
    """Resolve a condition key to a string value."""
    if key == "outcome":
        return outcome.status.value
    if key == "preferred_label":
        return outcome.preferred_label
    if key.startswith("context."):
        bare = key[len("context."):]
        val = context.get(key)
        if val is not None:
            return str(val)
        val = context.get(bare)
        if val is not None:
            return str(val)
        return ""
    # Direct context lookup for unqualified keys
    val = context.get(key)
    if val is not None:
        return str(val)
    return ""


def _evaluate_clause(clause: str, outcome: Outcome, context: Context) -> bool:
    """Evaluate a single clause."""
    clause = clause.strip()
    if not clause:
        return True
    if "!=" in clause:
        key, value = clause.split("!=", 1)
        return resolve_key(key.strip(), outcome, context) != value.strip()
    if "=" in clause:
        key, value = clause.split("=", 1)
        return resolve_key(key.strip(), outcome, context) == value.strip()
    # Bare key: truthy check
    return bool(resolve_key(clause, outcome, context))


def evaluate_condition(condition: str, outcome: Outcome, context: Context) -> bool:
    """Evaluate a condition expression. Empty condition is always true."""
    if not condition or not condition.strip():
        return True
    clauses = condition.split("&&")
    return all(_evaluate_clause(c, outcome, context) for c in clauses)
