"""DOT file parser for Attractor pipeline definitions."""

from __future__ import annotations

import re
from typing import Any

from attractor.graph import Edge, Graph, Node, Subgraph

# Attribute types for conversion
_BOOL_ATTRS = {"goal_gate", "auto_status", "allow_partial", "loop_restart"}
_INT_ATTRS = {"max_retries", "weight", "default_max_retry"}


def _strip_comments(text: str) -> str:
    """Remove // and /* */ comments."""
    # Block comments
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # Line comments
    text = re.sub(r"//[^\n]*", "", text)
    return text


def _parse_value(raw: str) -> str | int | float | bool:
    """Parse a DOT value string into a Python type."""
    # String (quoted)
    if raw.startswith('"') and raw.endswith('"'):
        s = raw[1:-1]
        s = s.replace('\\"', '"').replace("\\n", "\n").replace("\\t", "\t").replace("\\\\", "\\")
        return s
    # Boolean
    if raw == "true":
        return True
    if raw == "false":
        return False
    # Float
    if "." in raw:
        try:
            return float(raw)
        except ValueError:
            pass
    # Integer
    try:
        return int(raw)
    except ValueError:
        pass
    # Bare identifier as string
    return raw


def _tokenize(text: str) -> list[str]:
    """Tokenize DOT content into meaningful tokens."""
    tokens: list[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c in " \t\n\r":
            i += 1
            continue
        if c == ';':
            i += 1
            continue
        if c in "{}[],=":
            tokens.append(c)
            i += 1
            continue
        if c == '-' and i + 1 < len(text) and text[i + 1] == '>':
            tokens.append('->')
            i += 2
            continue
        if c == '"':
            # Quoted string
            j = i + 1
            while j < len(text):
                if text[j] == '\\' and j + 1 < len(text):
                    j += 2
                elif text[j] == '"':
                    j += 1
                    break
                else:
                    j += 1
            tokens.append(text[i:j])
            i = j
            continue
        # Identifier or number
        j = i
        while j < len(text) and text[j] not in " \t\n\r{}[],=;\"" and not (text[j] == '-' and j + 1 < len(text) and text[j + 1] == '>'):
            j += 1
        if j > i:
            tokens.append(text[i:j])
        i = j
    return tokens


def _coerce_attr(key: str, val: Any) -> Any:
    """Coerce attribute values to correct types."""
    if key in _BOOL_ATTRS:
        if isinstance(val, bool):
            return val
        return str(val).lower() == "true"
    if key in _INT_ATTRS:
        if isinstance(val, int):
            return val
        return int(val)
    return val


def _apply_attrs_to_node(node: Node, attrs: dict[str, Any]) -> None:
    """Apply parsed attribute dict to a Node."""
    for key, val in attrs.items():
        val = _coerce_attr(key, val)
        if key == "label":
            node.label = str(val)
        elif key == "shape":
            node.shape = str(val)
        elif key == "type":
            node.type = str(val)
        elif key == "prompt":
            node.prompt = str(val)
        elif key == "max_retries":
            node.max_retries = int(val)
        elif key == "goal_gate":
            node.goal_gate = bool(val)
        elif key == "retry_target":
            node.retry_target = str(val)
        elif key == "fallback_retry_target":
            node.fallback_retry_target = str(val)
        elif key == "fidelity":
            node.fidelity = str(val)
        elif key == "thread_id":
            node.thread_id = str(val)
        elif key == "class":
            node.classes = [c.strip() for c in str(val).split(",") if c.strip()]
        elif key == "timeout":
            node.timeout = str(val)
        elif key == "llm_model":
            node.llm_model = str(val)
        elif key == "llm_provider":
            node.llm_provider = str(val)
        elif key == "reasoning_effort":
            node.reasoning_effort = str(val)
        elif key == "auto_status":
            node.auto_status = bool(val)
        elif key == "allow_partial":
            node.allow_partial = bool(val)
        else:
            node.extra[key] = val


def _apply_attrs_to_edge(edge: Edge, attrs: dict[str, Any]) -> None:
    """Apply parsed attribute dict to an Edge."""
    for key, val in attrs.items():
        val = _coerce_attr(key, val)
        if key == "label":
            edge.label = str(val)
        elif key == "condition":
            edge.condition = str(val)
        elif key == "weight":
            edge.weight = int(val)
        elif key == "fidelity":
            edge.fidelity = str(val)
        elif key == "thread_id":
            edge.thread_id = str(val)
        elif key == "loop_restart":
            edge.loop_restart = bool(val)
        else:
            edge.extra[key] = val


class _Parser:
    """Recursive-descent parser for DOT digraph files."""

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def advance(self) -> str:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, value: str) -> str:
        tok = self.advance()
        if tok != value:
            raise SyntaxError(f"Expected '{value}', got '{tok}'")
        return tok

    def parse_graph(self) -> Graph:
        self.expect("digraph")
        name = self.advance()  # graph name
        self.expect("{")
        graph = Graph(name=name)
        self._parse_statements(graph, scope_node_defaults={}, scope_edge_defaults={})
        self.expect("}")
        return graph

    def _parse_statements(
        self, graph: Graph,
        scope_node_defaults: dict[str, Any],
        scope_edge_defaults: dict[str, Any],
        subgraph_name: str = "",
    ) -> None:
        while self.peek() and self.peek() != "}":
            tok = self.peek()

            if tok == "graph":
                self.advance()
                if self.peek() == "[":
                    attrs = self._parse_attr_block()
                    self._apply_graph_attrs(graph, attrs)
                continue

            if tok == "node":
                self.advance()
                if self.peek() == "[":
                    attrs = self._parse_attr_block()
                    scope_node_defaults.update(attrs)
                    graph.node_defaults.update({k: str(v) for k, v in attrs.items()})
                continue

            if tok == "edge":
                self.advance()
                if self.peek() == "[":
                    attrs = self._parse_attr_block()
                    scope_edge_defaults.update(attrs)
                    graph.edge_defaults.update({k: str(v) for k, v in attrs.items()})
                continue

            if tok == "subgraph":
                self.advance()
                sg_name = ""
                if self.peek() != "{":
                    sg_name = self.advance()
                self.expect("{")
                sg = Subgraph(name=sg_name)
                child_node_defaults = dict(scope_node_defaults)
                child_edge_defaults = dict(scope_edge_defaults)
                # Collect statements in subgraph
                old_pos = self.pos
                self._parse_statements(graph, child_node_defaults, child_edge_defaults, subgraph_name=sg_name)
                self.expect("}")

                # Parse label from graph if set
                if sg_name in graph.subgraphs:
                    sg = graph.subgraphs[sg_name]
                sg.node_defaults = {k: str(v) for k, v in child_node_defaults.items()}
                sg.edge_defaults = {k: str(v) for k, v in child_edge_defaults.items()}
                graph.subgraphs[sg_name] = sg
                continue

            # Could be a graph-level attr (ID = Value), node stmt, or edge stmt
            # Look ahead to determine
            if self._is_graph_attr_decl():
                key = self.advance()
                self.expect("=")
                val = _parse_value(self.advance())
                self._apply_graph_attrs(graph, {key: val})
                continue

            if self._is_edge_stmt():
                self._parse_edge_stmt(graph, scope_edge_defaults, scope_node_defaults, subgraph_name)
                continue

            # Node statement
            self._parse_node_stmt(graph, scope_node_defaults, subgraph_name)

    def _is_graph_attr_decl(self) -> bool:
        """Check if current position is ID = Value (graph attr declaration)."""
        if self.pos + 2 >= len(self.tokens):
            return False
        return self.tokens[self.pos + 1] == "=" and self.tokens[self.pos + 2] != "["

    def _is_edge_stmt(self) -> bool:
        """Check if current position starts an edge statement (has -> ahead)."""
        i = self.pos + 1
        while i < len(self.tokens) and self.tokens[i] not in ("{", "}", ";"):
            if self.tokens[i] == "->":
                return True
            if self.tokens[i] == "[":
                return False
            i += 1
        return False

    def _parse_node_stmt(
        self, graph: Graph,
        defaults: dict[str, Any],
        subgraph_name: str,
    ) -> None:
        node_id = self.advance()
        attrs = dict(defaults)
        if self.peek() == "[":
            attrs.update(self._parse_attr_block())

        if node_id not in graph.nodes:
            node = Node(id=node_id)
        else:
            node = graph.nodes[node_id]

        _apply_attrs_to_node(node, attrs)
        if subgraph_name:
            node.subgraph = subgraph_name
            sg = graph.subgraphs.setdefault(subgraph_name, Subgraph(name=subgraph_name))
            if node_id not in sg.node_ids:
                sg.node_ids.append(node_id)
            # Apply subgraph label-derived class
            if sg.label and sg.derived_class:
                if sg.derived_class not in node.classes:
                    node.classes.append(sg.derived_class)

        graph.nodes[node_id] = node

    def _parse_edge_stmt(
        self, graph: Graph,
        edge_defaults: dict[str, Any],
        node_defaults: dict[str, Any],
        subgraph_name: str,
    ) -> None:
        # Collect chain: A -> B -> C
        chain = [self.advance()]
        while self.peek() == "->":
            self.advance()  # consume ->
            chain.append(self.advance())

        attrs = dict(edge_defaults)
        if self.peek() == "[":
            attrs.update(self._parse_attr_block())

        # Ensure all nodes in chain exist
        for node_id in chain:
            if node_id not in graph.nodes:
                node = Node(id=node_id)
                _apply_attrs_to_node(node, node_defaults)
                if subgraph_name:
                    node.subgraph = subgraph_name
                graph.nodes[node_id] = node

        # Create edges for each pair
        for i in range(len(chain) - 1):
            edge = Edge(source=chain[i], target=chain[i + 1])
            _apply_attrs_to_edge(edge, attrs)
            graph.edges.append(edge)

    def _parse_attr_block(self) -> dict[str, Any]:
        """Parse [key=value, key=value, ...]"""
        self.expect("[")
        attrs: dict[str, Any] = {}
        while self.peek() and self.peek() != "]":
            if self.peek() == ",":
                self.advance()
                continue
            key = self.advance()
            self.expect("=")
            val = _parse_value(self.advance())
            attrs[key] = val
        self.expect("]")
        return attrs

    def _apply_graph_attrs(self, graph: Graph, attrs: dict[str, Any]) -> None:
        for key, val in attrs.items():
            if key == "goal":
                graph.goal = str(val)
            elif key == "label":
                graph.label = str(val)
            elif key == "model_stylesheet":
                graph.model_stylesheet = str(val)
            elif key == "default_max_retry":
                graph.default_max_retry = int(val)
            elif key == "retry_target":
                graph.retry_target = str(val)
            elif key == "fallback_retry_target":
                graph.fallback_retry_target = str(val)
            elif key == "default_fidelity":
                graph.default_fidelity = str(val)
            else:
                graph.extra[key] = val


def parse_dot(text: str) -> Graph:
    """Parse a DOT digraph string into a Graph."""
    cleaned = _strip_comments(text)
    tokens = _tokenize(cleaned)
    parser = _Parser(tokens)
    return parser.parse_graph()
