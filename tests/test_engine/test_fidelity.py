"""Tests for context fidelity resolution."""

from attractor.fidelity import resolve_fidelity, resolve_thread_id
from attractor.graph import Edge, Graph, Node, Subgraph


class TestResolveFidelity:
    def test_default(self):
        assert resolve_fidelity(Node(id="n"), None, Graph()) == "compact"

    def test_graph_default(self):
        g = Graph(default_fidelity="truncate")
        assert resolve_fidelity(Node(id="n"), None, g) == "truncate"

    def test_node_overrides_graph(self):
        g = Graph(default_fidelity="truncate")
        n = Node(id="n", fidelity="full")
        assert resolve_fidelity(n, None, g) == "full"

    def test_edge_overrides_node(self):
        n = Node(id="n", fidelity="compact")
        e = Edge(fidelity="summary:high")
        assert resolve_fidelity(n, e, Graph()) == "summary:high"

    def test_invalid_fidelity_falls_through(self):
        n = Node(id="n", fidelity="bogus")
        assert resolve_fidelity(n, None, Graph()) == "compact"

    def test_all_modes_recognized(self):
        modes = ["full", "truncate", "compact", "summary:low", "summary:medium", "summary:high"]
        for mode in modes:
            n = Node(id="n", fidelity=mode)
            assert resolve_fidelity(n, None, Graph()) == mode


class TestResolveThreadId:
    def test_node_thread_id(self):
        n = Node(id="n", thread_id="custom")
        assert resolve_thread_id(n, None, Graph()) == "custom"

    def test_edge_thread_id(self):
        n = Node(id="n")
        e = Edge(thread_id="edge-thread")
        assert resolve_thread_id(n, e, Graph()) == "edge-thread"

    def test_subgraph_derived_class(self):
        g = Graph(subgraphs={"cluster_loop": Subgraph(name="cluster_loop", label="Loop A")})
        n = Node(id="n", subgraph="cluster_loop")
        assert resolve_thread_id(n, None, g) == "loop-a"

    def test_prev_node_fallback(self):
        n = Node(id="n")
        assert resolve_thread_id(n, None, Graph(), prev_node_id="prev") == "prev"

    def test_self_id_fallback(self):
        n = Node(id="self_node")
        assert resolve_thread_id(n, None, Graph()) == "self_node"
