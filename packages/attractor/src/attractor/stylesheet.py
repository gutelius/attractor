"""Model stylesheet parser and resolver."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from attractor.graph import Graph, Node

_PROPERTIES = {"llm_model", "llm_provider", "reasoning_effort"}


@dataclass
class StyleRule:
    selector: str  # "*", ".classname", "#nodeid"
    specificity: int  # 0=*, 1=.class, 2=#id
    properties: dict[str, str] = field(default_factory=dict)
    order: int = 0  # declaration order for tiebreaking


def parse_stylesheet(text: str) -> list[StyleRule]:
    """Parse a CSS-like model stylesheet into rules."""
    rules: list[StyleRule] = []
    # Match: selector { declarations }
    pattern = re.compile(r"([*#.]\S*)\s*\{([^}]*)\}", re.DOTALL)
    for i, m in enumerate(pattern.finditer(text)):
        selector = m.group(1).strip()
        decl_text = m.group(2).strip()

        if selector == "*":
            specificity = 0
        elif selector.startswith("."):
            specificity = 1
        elif selector.startswith("#"):
            specificity = 2
        else:
            continue

        props: dict[str, str] = {}
        for decl in decl_text.split(";"):
            decl = decl.strip()
            if not decl:
                continue
            if ":" not in decl:
                continue
            key, val = decl.split(":", 1)
            key = key.strip()
            val = val.strip()
            if key in _PROPERTIES:
                props[key] = val

        if props:
            rules.append(StyleRule(selector=selector, specificity=specificity, properties=props, order=i))

    return rules


def _matches(rule: StyleRule, node: Node) -> bool:
    """Check if a rule's selector matches a node."""
    if rule.selector == "*":
        return True
    if rule.selector.startswith("#"):
        return rule.selector[1:] == node.id
    if rule.selector.startswith("."):
        return rule.selector[1:] in node.classes
    return False


def apply_stylesheet(graph: Graph) -> None:
    """Apply model_stylesheet rules to graph nodes.

    Only sets properties that the node does not already have explicitly.
    Higher specificity rules override lower. Equal specificity: later wins.
    """
    if not graph.model_stylesheet:
        return

    rules = parse_stylesheet(graph.model_stylesheet)

    for node in graph.nodes.values():
        # Collect applicable properties, respecting specificity
        resolved: dict[str, tuple[int, int, str]] = {}  # prop -> (specificity, order, value)
        for rule in rules:
            if _matches(rule, node):
                for prop, val in rule.properties.items():
                    existing = resolved.get(prop)
                    if existing is None or (rule.specificity, rule.order) >= (existing[0], existing[1]):
                        resolved[prop] = (rule.specificity, rule.order, val)

        # Apply only if node doesn't have explicit value
        for prop, (_, _, val) in resolved.items():
            if prop == "llm_model" and not node.llm_model:
                node.llm_model = val
            elif prop == "llm_provider" and not node.llm_provider:
                node.llm_provider = val
            elif prop == "reasoning_effort" and node.reasoning_effort == "high":
                # "high" is the default, only override if still default
                node.reasoning_effort = val
