"""Graph data structures for pipeline definitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Shape to handler type mapping
SHAPE_HANDLER_MAP: dict[str, str] = {
    "Mdiamond": "start",
    "Msquare": "exit",
    "box": "codergen",
    "hexagon": "wait.human",
    "diamond": "conditional",
    "component": "parallel",
    "tripleoctagon": "parallel.fan_in",
    "parallelogram": "tool",
    "house": "stack.manager_loop",
}


@dataclass
class Node:
    id: str = ""
    label: str = ""
    shape: str = "box"
    type: str = ""  # explicit handler type override
    prompt: str = ""
    max_retries: int = 0
    goal_gate: bool = False
    retry_target: str = ""
    fallback_retry_target: str = ""
    fidelity: str = ""
    thread_id: str = ""
    classes: list[str] = field(default_factory=list)
    timeout: str = ""
    llm_model: str = ""
    llm_provider: str = ""
    reasoning_effort: str = "high"
    auto_status: bool = False
    allow_partial: bool = False
    subgraph: str = ""  # containing subgraph name, if any
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def handler_type(self) -> str:
        """Resolve handler type from explicit type or shape."""
        if self.type:
            return self.type
        return SHAPE_HANDLER_MAP.get(self.shape, "codergen")

    @property
    def display_label(self) -> str:
        return self.label or self.id


@dataclass
class Edge:
    source: str = ""
    target: str = ""
    label: str = ""
    condition: str = ""
    weight: int = 0
    fidelity: str = ""
    thread_id: str = ""
    loop_restart: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Subgraph:
    name: str = ""
    label: str = ""
    node_defaults: dict[str, str] = field(default_factory=dict)
    edge_defaults: dict[str, str] = field(default_factory=dict)
    node_ids: list[str] = field(default_factory=list)

    @property
    def derived_class(self) -> str:
        """Derive CSS-like class from label."""
        if not self.label:
            return ""
        import re
        cls = self.label.lower().replace(" ", "-")
        cls = re.sub(r"[^a-z0-9-]", "", cls)
        return cls


@dataclass
class Graph:
    name: str = ""
    goal: str = ""
    label: str = ""
    model_stylesheet: str = ""
    default_max_retry: int = 50
    retry_target: str = ""
    fallback_retry_target: str = ""
    default_fidelity: str = ""
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    subgraphs: dict[str, Subgraph] = field(default_factory=dict)
    node_defaults: dict[str, str] = field(default_factory=dict)
    edge_defaults: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    def get_node(self, node_id: str) -> Node | None:
        return self.nodes.get(node_id)

    def start_node(self) -> Node | None:
        for n in self.nodes.values():
            if n.handler_type == "start":
                return n
        return None

    def exit_node(self) -> Node | None:
        for n in self.nodes.values():
            if n.handler_type == "exit":
                return n
        return None

    def outgoing_edges(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.source == node_id]

    def incoming_edges(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.target == node_id]
