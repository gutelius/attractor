"""Tests for model stylesheet parser and resolver."""

from attractor.graph import Graph, Node
from attractor.stylesheet import parse_stylesheet, apply_stylesheet, StyleRule


class TestParseStylesheet:
    def test_universal_selector(self):
        rules = parse_stylesheet("* { llm_model: claude-sonnet-4-5; }")
        assert len(rules) == 1
        assert rules[0].selector == "*"
        assert rules[0].specificity == 0
        assert rules[0].properties["llm_model"] == "claude-sonnet-4-5"

    def test_class_selector(self):
        rules = parse_stylesheet(".code { llm_model: claude-opus-4-6; llm_provider: anthropic; }")
        assert len(rules) == 1
        assert rules[0].selector == ".code"
        assert rules[0].specificity == 1
        assert rules[0].properties["llm_model"] == "claude-opus-4-6"
        assert rules[0].properties["llm_provider"] == "anthropic"

    def test_id_selector(self):
        rules = parse_stylesheet("#review { llm_model: gpt-5.2; reasoning_effort: high; }")
        assert len(rules) == 1
        assert rules[0].selector == "#review"
        assert rules[0].specificity == 2

    def test_multiple_rules(self):
        text = """
        * { llm_model: claude-sonnet-4-5; }
        .code { llm_model: claude-opus-4-6; }
        #critical { llm_model: gpt-5.2; }
        """
        rules = parse_stylesheet(text)
        assert len(rules) == 3
        assert rules[0].order < rules[1].order < rules[2].order

    def test_ignores_unknown_properties(self):
        rules = parse_stylesheet("* { color: red; llm_model: test; }")
        assert len(rules) == 1
        assert "color" not in rules[0].properties
        assert "llm_model" in rules[0].properties


class TestApplyStylesheet:
    def test_universal_applies_to_all(self):
        g = Graph(
            model_stylesheet="* { llm_model: claude-sonnet-4-5; llm_provider: anthropic; }",
            nodes={
                "A": Node(id="A"),
                "B": Node(id="B"),
            },
        )
        apply_stylesheet(g)
        assert g.nodes["A"].llm_model == "claude-sonnet-4-5"
        assert g.nodes["A"].llm_provider == "anthropic"
        assert g.nodes["B"].llm_model == "claude-sonnet-4-5"

    def test_class_selector_matches(self):
        g = Graph(
            model_stylesheet=".code { llm_model: claude-opus-4-6; }",
            nodes={
                "A": Node(id="A", classes=["code"]),
                "B": Node(id="B"),
            },
        )
        apply_stylesheet(g)
        assert g.nodes["A"].llm_model == "claude-opus-4-6"
        assert g.nodes["B"].llm_model == ""  # not matched

    def test_id_selector_matches(self):
        g = Graph(
            model_stylesheet="#review { llm_model: gpt-5.2; }",
            nodes={
                "review": Node(id="review"),
                "other": Node(id="other"),
            },
        )
        apply_stylesheet(g)
        assert g.nodes["review"].llm_model == "gpt-5.2"
        assert g.nodes["other"].llm_model == ""

    def test_specificity_ordering(self):
        g = Graph(
            model_stylesheet="""
                * { llm_model: default-model; }
                .code { llm_model: code-model; }
                #special { llm_model: special-model; }
            """,
            nodes={
                "special": Node(id="special", classes=["code"]),
                "coder": Node(id="coder", classes=["code"]),
                "plain": Node(id="plain"),
            },
        )
        apply_stylesheet(g)
        assert g.nodes["special"].llm_model == "special-model"  # #id wins
        assert g.nodes["coder"].llm_model == "code-model"       # .class wins over *
        assert g.nodes["plain"].llm_model == "default-model"    # * fallback

    def test_later_rules_override_equal_specificity(self):
        g = Graph(
            model_stylesheet="""
                * { llm_model: first; }
                * { llm_model: second; }
            """,
            nodes={"A": Node(id="A")},
        )
        apply_stylesheet(g)
        assert g.nodes["A"].llm_model == "second"

    def test_explicit_node_attrs_win(self):
        g = Graph(
            model_stylesheet="* { llm_model: default; llm_provider: anthropic; }",
            nodes={
                "A": Node(id="A", llm_model="explicit-model"),
            },
        )
        apply_stylesheet(g)
        assert g.nodes["A"].llm_model == "explicit-model"  # explicit wins
        assert g.nodes["A"].llm_provider == "anthropic"     # stylesheet fills gap

    def test_no_stylesheet(self):
        g = Graph(nodes={"A": Node(id="A")})
        apply_stylesheet(g)  # no-op, no crash
        assert g.nodes["A"].llm_model == ""

    def test_reasoning_effort(self):
        g = Graph(
            model_stylesheet="* { reasoning_effort: low; }",
            nodes={"A": Node(id="A")},
        )
        apply_stylesheet(g)
        assert g.nodes["A"].reasoning_effort == "low"
