"""Tests for DOT parser."""

import pytest

from attractor.parser import parse_dot


class TestMinimalGraph:
    def test_empty_graph(self):
        g = parse_dot('digraph G {}')
        assert g.name == "G"
        assert len(g.nodes) == 0

    def test_single_node(self):
        g = parse_dot('digraph G { A }')
        assert "A" in g.nodes

    def test_single_edge(self):
        g = parse_dot('digraph G { A -> B }')
        assert "A" in g.nodes
        assert "B" in g.nodes
        assert len(g.edges) == 1
        assert g.edges[0].source == "A"
        assert g.edges[0].target == "B"


class TestNodeAttributes:
    def test_node_with_attrs(self):
        g = parse_dot('digraph G { A [label="Start", shape=Mdiamond] }')
        assert g.nodes["A"].label == "Start"
        assert g.nodes["A"].shape == "Mdiamond"

    def test_node_boolean_attrs(self):
        g = parse_dot('digraph G { A [goal_gate=true, auto_status=false] }')
        assert g.nodes["A"].goal_gate is True
        assert g.nodes["A"].auto_status is False

    def test_node_integer_attrs(self):
        g = parse_dot('digraph G { A [max_retries=3] }')
        assert g.nodes["A"].max_retries == 3

    def test_node_class_attr(self):
        g = parse_dot('digraph G { A [class="code,critical"] }')
        assert g.nodes["A"].classes == ["code", "critical"]

    def test_node_prompt(self):
        g = parse_dot('digraph G { A [prompt="Write tests for $goal"] }')
        assert g.nodes["A"].prompt == "Write tests for $goal"


class TestEdgeAttributes:
    def test_edge_with_label(self):
        g = parse_dot('digraph G { A -> B [label="success"] }')
        assert g.edges[0].label == "success"

    def test_edge_with_condition(self):
        g = parse_dot('digraph G { A -> B [condition="outcome=success"] }')
        assert g.edges[0].condition == "outcome=success"

    def test_edge_weight(self):
        g = parse_dot('digraph G { A -> B [weight=10] }')
        assert g.edges[0].weight == 10

    def test_edge_loop_restart(self):
        g = parse_dot('digraph G { A -> B [loop_restart=true] }')
        assert g.edges[0].loop_restart is True


class TestChainedEdges:
    def test_three_node_chain(self):
        g = parse_dot('digraph G { A -> B -> C }')
        assert len(g.edges) == 2
        assert g.edges[0].source == "A" and g.edges[0].target == "B"
        assert g.edges[1].source == "B" and g.edges[1].target == "C"

    def test_chain_with_attrs(self):
        g = parse_dot('digraph G { A -> B -> C [label="next"] }')
        assert g.edges[0].label == "next"
        assert g.edges[1].label == "next"


class TestSubgraphs:
    def test_basic_subgraph(self):
        g = parse_dot('''
        digraph G {
            subgraph cluster_loop {
                A [label="Task A"]
                B [label="Task B"]
            }
        }
        ''')
        assert "A" in g.nodes
        assert "B" in g.nodes
        assert "cluster_loop" in g.subgraphs

    def test_subgraph_node_defaults(self):
        g = parse_dot('''
        digraph G {
            subgraph cluster_x {
                node [timeout="900s"]
                A
                B [timeout="1800s"]
            }
        }
        ''')
        # A inherits default, B overrides
        assert g.nodes["A"].timeout == "900s"
        assert g.nodes["B"].timeout == "1800s"


class TestGraphAttributes:
    def test_graph_block(self):
        g = parse_dot('''
        digraph G {
            graph [goal="Build a calculator"]
        }
        ''')
        assert g.goal == "Build a calculator"

    def test_top_level_attr(self):
        g = parse_dot('''
        digraph G {
            goal = "Build a calculator"
        }
        ''')
        assert g.goal == "Build a calculator"

    def test_default_max_retry(self):
        g = parse_dot('digraph G { default_max_retry = 10 }')
        assert g.default_max_retry == 10


class TestComments:
    def test_line_comments(self):
        g = parse_dot('''
        digraph G {
            // This is a comment
            A -> B  // inline comment
        }
        ''')
        assert len(g.edges) == 1

    def test_block_comments(self):
        g = parse_dot('''
        digraph G {
            /* This is a
               block comment */
            A -> B
        }
        ''')
        assert len(g.edges) == 1


class TestValueTypes:
    def test_string_escapes(self):
        g = parse_dot(r'digraph G { A [label="line1\nline2"] }')
        assert "\n" in g.nodes["A"].label

    def test_integer(self):
        g = parse_dot('digraph G { A [max_retries=5] }')
        assert g.nodes["A"].max_retries == 5

    def test_boolean(self):
        g = parse_dot('digraph G { A [goal_gate=true] }')
        assert g.nodes["A"].goal_gate is True


class TestNodeEdgeDefaults:
    def test_node_defaults(self):
        g = parse_dot('''
        digraph G {
            node [shape=box, timeout="900s"]
            A
            B
        }
        ''')
        assert g.nodes["A"].shape == "box"
        assert g.nodes["A"].timeout == "900s"
        assert g.nodes["B"].shape == "box"

    def test_edge_defaults(self):
        g = parse_dot('''
        digraph G {
            edge [weight=5]
            A -> B
            C -> D
        }
        ''')
        assert g.edges[0].weight == 5
        assert g.edges[1].weight == 5


class TestFullPipeline:
    def test_realistic_pipeline(self):
        g = parse_dot('''
        digraph build_calculator {
            goal = "Build a calculator app"

            Start [shape=Mdiamond]
            Plan [label="Plan implementation", prompt="Create a plan for $goal"]
            Review [shape=hexagon, label="Review plan"]
            Implement [label="Write code", max_retries=3, goal_gate=true]
            Test [label="Run tests"]
            Exit [shape=Msquare]

            Start -> Plan
            Plan -> Review
            Review -> Implement [label="approved", condition="outcome=success"]
            Review -> Plan [label="revise", condition="outcome=fail"]
            Implement -> Test
            Test -> Exit [label="pass", condition="outcome=success"]
            Test -> Implement [label="fix", condition="outcome=fail"]
        }
        ''')
        assert g.name == "build_calculator"
        assert g.goal == "Build a calculator app"
        assert len(g.nodes) == 6
        assert len(g.edges) == 7
        assert g.start_node().id == "Start"
        assert g.exit_node().id == "Exit"
        assert g.nodes["Implement"].goal_gate is True
        assert g.nodes["Implement"].max_retries == 3
        assert g.nodes["Review"].handler_type == "wait.human"
