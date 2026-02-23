"""Tests for graph data structures."""

from attractor.graph import Node, Edge, Graph, Subgraph, SHAPE_HANDLER_MAP


class TestNode:
    def test_handler_type_from_shape(self):
        n = Node(id="start", shape="Mdiamond")
        assert n.handler_type == "start"

    def test_handler_type_explicit_override(self):
        n = Node(id="custom", shape="box", type="my_handler")
        assert n.handler_type == "my_handler"

    def test_default_shape_is_box(self):
        n = Node(id="task")
        assert n.shape == "box"
        assert n.handler_type == "codergen"

    def test_display_label_fallback(self):
        n = Node(id="my_node")
        assert n.display_label == "my_node"
        n.label = "My Node"
        assert n.display_label == "My Node"

    def test_all_shapes_mapped(self):
        expected = {
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
        assert SHAPE_HANDLER_MAP == expected


class TestEdge:
    def test_basic_edge(self):
        e = Edge(source="A", target="B", label="next")
        assert e.source == "A"
        assert e.target == "B"
        assert e.label == "next"

    def test_defaults(self):
        e = Edge()
        assert e.weight == 0
        assert e.condition == ""
        assert not e.loop_restart


class TestSubgraph:
    def test_derived_class(self):
        sg = Subgraph(name="cluster_loop", label="Loop A")
        assert sg.derived_class == "loop-a"

    def test_derived_class_empty(self):
        sg = Subgraph(name="cluster_x")
        assert sg.derived_class == ""

    def test_derived_class_special_chars(self):
        sg = Subgraph(name="c", label="Test & Review!")
        assert sg.derived_class == "test--review"


class TestGraph:
    def test_start_and_exit_nodes(self):
        g = Graph(
            nodes={
                "s": Node(id="s", shape="Mdiamond"),
                "e": Node(id="e", shape="Msquare"),
                "t": Node(id="t", shape="box"),
            }
        )
        assert g.start_node().id == "s"
        assert g.exit_node().id == "e"

    def test_outgoing_edges(self):
        g = Graph(
            edges=[
                Edge(source="A", target="B"),
                Edge(source="A", target="C"),
                Edge(source="B", target="C"),
            ]
        )
        out = g.outgoing_edges("A")
        assert len(out) == 2

    def test_incoming_edges(self):
        g = Graph(
            edges=[
                Edge(source="A", target="C"),
                Edge(source="B", target="C"),
            ]
        )
        inc = g.incoming_edges("C")
        assert len(inc) == 2

    def test_get_node(self):
        g = Graph(nodes={"x": Node(id="x", label="X Node")})
        assert g.get_node("x").label == "X Node"
        assert g.get_node("y") is None

    def test_defaults(self):
        g = Graph()
        assert g.default_max_retry == 50
        assert g.goal == ""
