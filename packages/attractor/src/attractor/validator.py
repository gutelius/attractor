"""Graph validation and linting."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from attractor.graph import Graph, SHAPE_HANDLER_MAP

_VALID_FIDELITY = {"full", "truncate", "compact", "summary:low", "summary:medium", "summary:high"}


class Severity(Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Diagnostic:
    rule: str
    severity: Severity
    message: str
    node_id: str = ""
    edge: tuple[str, str] | None = None
    fix: str = ""


class ValidationError(Exception):
    def __init__(self, diagnostics: list[Diagnostic]) -> None:
        self.diagnostics = diagnostics
        msgs = "; ".join(f"[{d.rule}] {d.message}" for d in diagnostics)
        super().__init__(msgs)


class LintRule(Protocol):
    name: str
    def apply(self, graph: Graph) -> list[Diagnostic]: ...


# --- Built-in rules ---

def _check_start_node(g: Graph) -> list[Diagnostic]:
    starts = [n for n in g.nodes.values() if n.handler_type == "start"]
    if len(starts) == 0:
        return [Diagnostic(rule="start_node", severity=Severity.ERROR,
                           message="Pipeline must have exactly one start node (shape=Mdiamond). Found none.",
                           fix="Add a node with shape=Mdiamond")]
    if len(starts) > 1:
        ids = ", ".join(n.id for n in starts)
        return [Diagnostic(rule="start_node", severity=Severity.ERROR,
                           message=f"Pipeline must have exactly one start node. Found {len(starts)}: {ids}.",
                           fix="Remove extra start nodes")]
    return []


def _check_terminal_node(g: Graph) -> list[Diagnostic]:
    exits = [n for n in g.nodes.values() if n.handler_type == "exit"]
    if len(exits) == 0:
        return [Diagnostic(rule="terminal_node", severity=Severity.ERROR,
                           message="Pipeline must have at least one terminal node (shape=Msquare). Found none.",
                           fix="Add a node with shape=Msquare")]
    return []


def _check_reachability(g: Graph) -> list[Diagnostic]:
    start = g.start_node()
    if start is None:
        return []  # start_node rule already catches this
    visited: set[str] = set()
    stack = [start.id]
    while stack:
        nid = stack.pop()
        if nid in visited:
            continue
        visited.add(nid)
        for e in g.outgoing_edges(nid):
            if e.target in g.nodes:
                stack.append(e.target)
    unreachable = set(g.nodes.keys()) - visited
    if unreachable:
        ids = ", ".join(sorted(unreachable))
        return [Diagnostic(rule="reachability", severity=Severity.ERROR,
                           message=f"Unreachable nodes: {ids}",
                           fix="Add edges from reachable nodes or remove unreachable ones")]
    return []


def _check_edge_target_exists(g: Graph) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for e in g.edges:
        if e.source not in g.nodes:
            diags.append(Diagnostic(rule="edge_target_exists", severity=Severity.ERROR,
                                    message=f"Edge source '{e.source}' does not exist",
                                    edge=(e.source, e.target)))
        if e.target not in g.nodes:
            diags.append(Diagnostic(rule="edge_target_exists", severity=Severity.ERROR,
                                    message=f"Edge target '{e.target}' does not exist",
                                    edge=(e.source, e.target)))
    return diags


def _check_start_no_incoming(g: Graph) -> list[Diagnostic]:
    start = g.start_node()
    if start is None:
        return []
    incoming = g.incoming_edges(start.id)
    if incoming:
        return [Diagnostic(rule="start_no_incoming", severity=Severity.ERROR,
                           message=f"Start node '{start.id}' must have no incoming edges, found {len(incoming)}",
                           node_id=start.id)]
    return []


def _check_exit_no_outgoing(g: Graph) -> list[Diagnostic]:
    exit_node = g.exit_node()
    if exit_node is None:
        return []
    outgoing = g.outgoing_edges(exit_node.id)
    if outgoing:
        return [Diagnostic(rule="exit_no_outgoing", severity=Severity.ERROR,
                           message=f"Exit node '{exit_node.id}' must have no outgoing edges, found {len(outgoing)}",
                           node_id=exit_node.id)]
    return []


def _check_fidelity_valid(g: Graph) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for n in g.nodes.values():
        if n.fidelity and n.fidelity not in _VALID_FIDELITY:
            diags.append(Diagnostic(rule="fidelity_valid", severity=Severity.WARNING,
                                    message=f"Node '{n.id}' has invalid fidelity '{n.fidelity}'",
                                    node_id=n.id,
                                    fix=f"Use one of: {', '.join(sorted(_VALID_FIDELITY))}"))
    return diags


def _check_retry_target_exists(g: Graph) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for n in g.nodes.values():
        if n.retry_target and n.retry_target not in g.nodes:
            diags.append(Diagnostic(rule="retry_target_exists", severity=Severity.WARNING,
                                    message=f"Node '{n.id}' retry_target '{n.retry_target}' does not exist",
                                    node_id=n.id))
        if n.fallback_retry_target and n.fallback_retry_target not in g.nodes:
            diags.append(Diagnostic(rule="retry_target_exists", severity=Severity.WARNING,
                                    message=f"Node '{n.id}' fallback_retry_target '{n.fallback_retry_target}' does not exist",
                                    node_id=n.id))
    return diags


def _check_goal_gate_has_retry(g: Graph) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for n in g.nodes.values():
        if n.goal_gate and not n.retry_target and not n.fallback_retry_target:
            diags.append(Diagnostic(rule="goal_gate_has_retry", severity=Severity.WARNING,
                                    message=f"Node '{n.id}' has goal_gate=true but no retry_target or fallback_retry_target",
                                    node_id=n.id,
                                    fix="Add retry_target attribute"))
    return diags


def _check_prompt_on_llm_nodes(g: Graph) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for n in g.nodes.values():
        if n.handler_type == "codergen" and not n.prompt and not n.label:
            diags.append(Diagnostic(rule="prompt_on_llm_nodes", severity=Severity.WARNING,
                                    message=f"Node '{n.id}' resolves to codergen handler but has no prompt or label",
                                    node_id=n.id,
                                    fix="Add a prompt or label attribute"))
    return diags


_BUILT_IN_RULES = [
    _check_start_node,
    _check_terminal_node,
    _check_reachability,
    _check_edge_target_exists,
    _check_start_no_incoming,
    _check_exit_no_outgoing,
    _check_fidelity_valid,
    _check_retry_target_exists,
    _check_goal_gate_has_retry,
    _check_prompt_on_llm_nodes,
]


def validate(graph: Graph, extra_rules: list[Any] | None = None) -> list[Diagnostic]:
    """Run all lint rules against a graph and return diagnostics."""
    diags: list[Diagnostic] = []
    for rule_fn in _BUILT_IN_RULES:
        diags.extend(rule_fn(graph))
    if extra_rules:
        for rule in extra_rules:
            diags.extend(rule.apply(graph))
    return diags


def validate_or_raise(graph: Graph, extra_rules: list[Any] | None = None) -> list[Diagnostic]:
    """Validate and raise ValidationError if any ERROR-severity diagnostics."""
    diags = validate(graph, extra_rules)
    errors = [d for d in diags if d.severity == Severity.ERROR]
    if errors:
        raise ValidationError(errors)
    return diags
