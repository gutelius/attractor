"""Context fidelity resolution."""

from __future__ import annotations

from attractor.graph import Edge, Graph, Node


_VALID_MODES = {"full", "truncate", "compact", "summary:low", "summary:medium", "summary:high"}


def resolve_fidelity(node: Node, incoming_edge: Edge | None, graph: Graph) -> str:
    """Resolve fidelity mode using precedence: edge > node > graph > default."""
    # 1. Edge fidelity
    if incoming_edge and incoming_edge.fidelity and incoming_edge.fidelity in _VALID_MODES:
        return incoming_edge.fidelity
    # 2. Node fidelity
    if node.fidelity and node.fidelity in _VALID_MODES:
        return node.fidelity
    # 3. Graph default
    if graph.default_fidelity and graph.default_fidelity in _VALID_MODES:
        return graph.default_fidelity
    # 4. Default
    return "compact"


def resolve_thread_id(node: Node, incoming_edge: Edge | None, graph: Graph, prev_node_id: str = "") -> str:
    """Resolve thread ID for full-fidelity session reuse."""
    # 1. Node thread_id
    if node.thread_id:
        return node.thread_id
    # 2. Edge thread_id
    if incoming_edge and incoming_edge.thread_id:
        return incoming_edge.thread_id
    # 3. Subgraph derived class
    if node.subgraph:
        sg = graph.subgraphs.get(node.subgraph)
        if sg and sg.derived_class:
            return sg.derived_class
    # 4. Previous node ID
    return prev_node_id or node.id
