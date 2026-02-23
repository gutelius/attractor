"""Tests for graph validator."""

import pytest

from attractor.graph import Node, Edge, Graph, SHAPE_HANDLER_MAP
from attractor.validator import (
    Diagnostic,
    Severity,
    ValidationError,
    validate,
    validate_or_raise,
)


def _simple_graph(**overrides) -> Graph:
    """Build a minimal valid graph: Start -> Task -> Exit."""
    g = Graph(
        name="test",
        nodes={
            "Start": Node(id="Start", shape="Mdiamond"),
            "Task": Node(id="Task", shape="box", label="Do something"),
            "Exit": Node(id="Exit", shape="Msquare"),
        },
        edges=[
            Edge(source="Start", target="Task"),
            Edge(source="Task", target="Exit"),
        ],
    )
    for k, v in overrides.items():
        setattr(g, k, v)
    return g


class TestStartNode:
    def test_valid_single_start(self):
        diags = validate(_simple_graph())
        errors = [d for d in diags if d.rule == "start_node"]
        assert len(errors) == 0

    def test_no_start_node(self):
        g = Graph(
            nodes={
                "A": Node(id="A", shape="box"),
                "Exit": Node(id="Exit", shape="Msquare"),
            },
            edges=[Edge(source="A", target="Exit")],
        )
        diags = validate(g)
        start_errors = [d for d in diags if d.rule == "start_node" and d.severity == Severity.ERROR]
        assert len(start_errors) == 1

    def test_multiple_start_nodes(self):
        g = Graph(
            nodes={
                "S1": Node(id="S1", shape="Mdiamond"),
                "S2": Node(id="S2", shape="Mdiamond"),
                "Exit": Node(id="Exit", shape="Msquare"),
            },
            edges=[
                Edge(source="S1", target="Exit"),
                Edge(source="S2", target="Exit"),
            ],
        )
        diags = validate(g)
        start_errors = [d for d in diags if d.rule == "start_node" and d.severity == Severity.ERROR]
        assert len(start_errors) == 1
        assert "exactly one" in start_errors[0].message.lower()


class TestTerminalNode:
    def test_valid_single_exit(self):
        diags = validate(_simple_graph())
        errors = [d for d in diags if d.rule == "terminal_node"]
        assert len(errors) == 0

    def test_no_exit_node(self):
        g = Graph(
            nodes={
                "Start": Node(id="Start", shape="Mdiamond"),
                "A": Node(id="A", shape="box"),
            },
            edges=[Edge(source="Start", target="A")],
        )
        diags = validate(g)
        exit_errors = [d for d in diags if d.rule == "terminal_node" and d.severity == Severity.ERROR]
        assert len(exit_errors) == 1


class TestReachability:
    def test_all_reachable(self):
        diags = validate(_simple_graph())
        reach_errors = [d for d in diags if d.rule == "reachability"]
        assert len(reach_errors) == 0

    def test_unreachable_node(self):
        g = Graph(
            nodes={
                "Start": Node(id="Start", shape="Mdiamond"),
                "Task": Node(id="Task", shape="box"),
                "Orphan": Node(id="Orphan", shape="box"),
                "Exit": Node(id="Exit", shape="Msquare"),
            },
            edges=[
                Edge(source="Start", target="Task"),
                Edge(source="Task", target="Exit"),
            ],
        )
        diags = validate(g)
        reach_errors = [d for d in diags if d.rule == "reachability" and d.severity == Severity.ERROR]
        assert len(reach_errors) == 1
        assert "Orphan" in reach_errors[0].message


class TestEdgeTargetExists:
    def test_valid_edges(self):
        diags = validate(_simple_graph())
        errors = [d for d in diags if d.rule == "edge_target_exists"]
        assert len(errors) == 0

    def test_edge_to_missing_node(self):
        g = Graph(
            nodes={
                "Start": Node(id="Start", shape="Mdiamond"),
                "Exit": Node(id="Exit", shape="Msquare"),
            },
            edges=[
                Edge(source="Start", target="Missing"),
                Edge(source="Start", target="Exit"),
            ],
        )
        diags = validate(g)
        errors = [d for d in diags if d.rule == "edge_target_exists" and d.severity == Severity.ERROR]
        assert len(errors) == 1
        assert "Missing" in errors[0].message

    def test_edge_from_missing_node(self):
        g = Graph(
            nodes={
                "Start": Node(id="Start", shape="Mdiamond"),
                "Exit": Node(id="Exit", shape="Msquare"),
            },
            edges=[
                Edge(source="Ghost", target="Exit"),
                Edge(source="Start", target="Exit"),
            ],
        )
        diags = validate(g)
        errors = [d for d in diags if d.rule == "edge_target_exists" and d.severity == Severity.ERROR]
        assert len(errors) >= 1


class TestStartNoIncoming:
    def test_start_no_incoming(self):
        diags = validate(_simple_graph())
        errors = [d for d in diags if d.rule == "start_no_incoming"]
        assert len(errors) == 0

    def test_start_has_incoming(self):
        g = Graph(
            nodes={
                "Start": Node(id="Start", shape="Mdiamond"),
                "Task": Node(id="Task", shape="box"),
                "Exit": Node(id="Exit", shape="Msquare"),
            },
            edges=[
                Edge(source="Start", target="Task"),
                Edge(source="Task", target="Start"),
                Edge(source="Task", target="Exit"),
            ],
        )
        diags = validate(g)
        errors = [d for d in diags if d.rule == "start_no_incoming" and d.severity == Severity.ERROR]
        assert len(errors) == 1


class TestExitNoOutgoing:
    def test_exit_no_outgoing(self):
        diags = validate(_simple_graph())
        errors = [d for d in diags if d.rule == "exit_no_outgoing"]
        assert len(errors) == 0

    def test_exit_has_outgoing(self):
        g = Graph(
            nodes={
                "Start": Node(id="Start", shape="Mdiamond"),
                "Task": Node(id="Task", shape="box"),
                "Exit": Node(id="Exit", shape="Msquare"),
            },
            edges=[
                Edge(source="Start", target="Task"),
                Edge(source="Task", target="Exit"),
                Edge(source="Exit", target="Task"),
            ],
        )
        diags = validate(g)
        errors = [d for d in diags if d.rule == "exit_no_outgoing" and d.severity == Severity.ERROR]
        assert len(errors) == 1


class TestWarnings:
    def test_fidelity_valid(self):
        g = _simple_graph()
        g.nodes["Task"].fidelity = "full"
        diags = validate(g)
        warns = [d for d in diags if d.rule == "fidelity_valid"]
        assert len(warns) == 0

    def test_fidelity_invalid(self):
        g = _simple_graph()
        g.nodes["Task"].fidelity = "bogus"
        diags = validate(g)
        warns = [d for d in diags if d.rule == "fidelity_valid" and d.severity == Severity.WARNING]
        assert len(warns) == 1

    def test_retry_target_exists(self):
        g = _simple_graph()
        g.nodes["Task"].retry_target = "NonExistent"
        diags = validate(g)
        warns = [d for d in diags if d.rule == "retry_target_exists" and d.severity == Severity.WARNING]
        assert len(warns) == 1

    def test_goal_gate_has_retry(self):
        g = _simple_graph()
        g.nodes["Task"].goal_gate = True
        # No retry_target set
        diags = validate(g)
        warns = [d for d in diags if d.rule == "goal_gate_has_retry" and d.severity == Severity.WARNING]
        assert len(warns) == 1

    def test_goal_gate_with_retry_no_warning(self):
        g = _simple_graph()
        g.nodes["Task"].goal_gate = True
        g.nodes["Task"].retry_target = "Task"
        diags = validate(g)
        warns = [d for d in diags if d.rule == "goal_gate_has_retry"]
        assert len(warns) == 0

    def test_prompt_on_llm_nodes(self):
        g = _simple_graph()
        g.nodes["Task"].label = ""  # No label or prompt
        g.nodes["Task"].prompt = ""
        diags = validate(g)
        warns = [d for d in diags if d.rule == "prompt_on_llm_nodes" and d.severity == Severity.WARNING]
        assert len(warns) == 1


class TestValidateOrRaise:
    def test_valid_graph_returns_diagnostics(self):
        diags = validate_or_raise(_simple_graph())
        # May have warnings but no errors
        errors = [d for d in diags if d.severity == Severity.ERROR]
        assert len(errors) == 0

    def test_invalid_graph_raises(self):
        g = Graph(nodes={"A": Node(id="A", shape="box")})
        with pytest.raises(ValidationError) as exc_info:
            validate_or_raise(g)
        assert "start_node" in str(exc_info.value)


class TestCustomRules:
    def test_extra_rule(self):
        class NoTaskNamedFoo:
            name = "no_foo"
            def apply(self, graph):
                return [
                    Diagnostic(rule="no_foo", severity=Severity.ERROR, message="Node 'Foo' not allowed")
                    for nid in graph.nodes if nid == "Foo"
                ]

        g = _simple_graph()
        g.nodes["Foo"] = Node(id="Foo", shape="box")
        g.edges.append(Edge(source="Start", target="Foo"))
        g.edges.append(Edge(source="Foo", target="Exit"))

        diags = validate(g, extra_rules=[NoTaskNamedFoo()])
        foo_errors = [d for d in diags if d.rule == "no_foo"]
        assert len(foo_errors) == 1
