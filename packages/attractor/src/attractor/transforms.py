"""Pipeline transforms applied after parsing and before validation."""

from __future__ import annotations

from typing import Protocol

from attractor.graph import Graph
from attractor.stylesheet import apply_stylesheet


class Transform(Protocol):
    """Interface for graph transforms."""
    def apply(self, graph: Graph) -> Graph: ...


class VariableExpansionTransform:
    """Expands $goal in node prompts."""

    def apply(self, graph: Graph) -> Graph:
        for node in graph.nodes.values():
            if node.prompt and "$goal" in node.prompt:
                node.prompt = node.prompt.replace("$goal", graph.goal)
        return graph


class StylesheetTransform:
    """Applies model_stylesheet to resolve LLM config per node."""

    def apply(self, graph: Graph) -> Graph:
        apply_stylesheet(graph)
        return graph


def build_preamble(
    graph: Graph,
    completed_nodes: list[str],
    node_outcomes: dict[str, str],
    context_snapshot: dict[str, object],
    fidelity: str,
) -> str:
    """Synthesize a context preamble based on fidelity mode."""
    if fidelity == "truncate":
        lines = [f"Pipeline: {graph.name}", f"Goal: {graph.goal}"]
        return "\n".join(lines)

    if fidelity == "compact":
        lines = [f"Pipeline: {graph.name}", f"Goal: {graph.goal}", ""]
        if completed_nodes:
            lines.append("Completed stages:")
            for nid in completed_nodes:
                status = node_outcomes.get(nid, "unknown")
                lines.append(f"  - {nid}: {status}")
        if context_snapshot:
            lines.append("")
            lines.append("Context:")
            for k, v in list(context_snapshot.items())[:20]:
                lines.append(f"  {k}: {v}")
        return "\n".join(lines)

    if fidelity.startswith("summary:"):
        level = fidelity.split(":")[1]
        lines = [f"Pipeline: {graph.name}", f"Goal: {graph.goal}", ""]
        if level in ("medium", "high"):
            if completed_nodes:
                recent = completed_nodes[-5:] if level == "medium" else completed_nodes[-10:]
                lines.append("Recent stages:")
                for nid in recent:
                    status = node_outcomes.get(nid, "unknown")
                    lines.append(f"  - {nid}: {status}")
        if level == "high" and context_snapshot:
            lines.append("")
            lines.append("Active context:")
            for k, v in list(context_snapshot.items())[:30]:
                lines.append(f"  {k}: {v}")
        elif level == "low":
            lines.append(f"Completed {len(completed_nodes)} stages.")
        return "\n".join(lines)

    return f"Pipeline: {graph.name}\nGoal: {graph.goal}"


def prepare_pipeline(dot_source: str, transforms: list[Transform] | None = None) -> Graph:
    """Parse, transform, and return a graph ready for validation."""
    from attractor.parser import parse_dot

    graph = parse_dot(dot_source)
    # Built-in transforms
    graph = VariableExpansionTransform().apply(graph)
    graph = StylesheetTransform().apply(graph)
    # Custom transforms
    if transforms:
        for t in transforms:
            graph = t.apply(graph)
    return graph
