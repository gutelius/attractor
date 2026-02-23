"""Tests for pipeline transforms."""

from attractor.graph import Graph, Node
from attractor.transforms import (
    VariableExpansionTransform,
    StylesheetTransform,
    build_preamble,
    prepare_pipeline,
)


class TestVariableExpansionTransform:
    def test_expands_goal(self):
        g = Graph(goal="Build a calculator", nodes={"A": Node(id="A", prompt="Implement $goal")})
        t = VariableExpansionTransform()
        g = t.apply(g)
        assert g.nodes["A"].prompt == "Implement Build a calculator"

    def test_no_goal_no_change(self):
        g = Graph(nodes={"A": Node(id="A", prompt="No variables here")})
        t = VariableExpansionTransform()
        g = t.apply(g)
        assert g.nodes["A"].prompt == "No variables here"


class TestStylesheetTransform:
    def test_applies_stylesheet(self):
        g = Graph(
            model_stylesheet="* { llm_model: test-model; }",
            nodes={"A": Node(id="A")},
        )
        t = StylesheetTransform()
        g = t.apply(g)
        assert g.nodes["A"].llm_model == "test-model"


class TestBuildPreamble:
    def test_truncate_mode(self):
        g = Graph(name="test", goal="Build things")
        p = build_preamble(g, [], {}, {}, "truncate")
        assert "Goal: Build things" in p
        assert "Completed" not in p

    def test_compact_mode(self):
        g = Graph(name="test", goal="Build things")
        p = build_preamble(g, ["Start", "Plan"], {"Start": "success", "Plan": "success"}, {"x": 1}, "compact")
        assert "Completed stages:" in p
        assert "Plan: success" in p
        assert "x: 1" in p

    def test_summary_low(self):
        g = Graph(name="test", goal="Go")
        p = build_preamble(g, ["A", "B", "C"], {}, {}, "summary:low")
        assert "Completed 3 stages" in p

    def test_summary_high(self):
        g = Graph(name="test", goal="Go")
        p = build_preamble(g, ["A", "B"], {"A": "success", "B": "fail"}, {"key": "val"}, "summary:high")
        assert "Recent stages:" in p
        assert "Active context:" in p
        assert "key: val" in p


class TestPreparePipeline:
    def test_full_pipeline(self):
        dot = '''
        digraph G {
            goal = "Build it"
            model_stylesheet = "* { llm_model: test-model; }"
            Start [shape=Mdiamond]
            Task [prompt="Implement $goal"]
            Exit [shape=Msquare]
            Start -> Task -> Exit
        }
        '''
        g = prepare_pipeline(dot)
        assert g.nodes["Task"].prompt == "Implement Build it"
        assert g.nodes["Task"].llm_model == "test-model"
