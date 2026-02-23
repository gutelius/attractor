"""Pipeline execution engine."""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from typing import Any

from attractor.checkpoint import Checkpoint
from attractor.conditions import evaluate_condition
from attractor.context import Context
from attractor.graph import Edge, Graph, Node
from attractor.handlers.base import Handler, HandlerRegistry
from attractor.handlers.start_exit import StartHandler, ExitHandler
from attractor.handlers.conditional import ConditionalHandler
from attractor.handlers.codergen import CodergenHandler
from attractor.handlers.human import WaitForHumanHandler
from attractor.handlers.parallel import ParallelHandler, FanInHandler
from attractor.handlers.tool import ToolHandler
from attractor.handlers.manager import ManagerLoopHandler
from attractor.interviewer import AutoApproveInterviewer
from attractor.outcome import Outcome, StageStatus
from attractor.parser import parse_dot
from attractor.stylesheet import apply_stylesheet
from attractor.transforms import VariableExpansionTransform, StylesheetTransform
from attractor.validator import validate_or_raise


@dataclass
class EngineConfig:
    logs_root: str = ""
    dry_run: bool = False
    max_steps: int = 1000
    interviewer: Any = None
    codergen_backend: Any = None
    extra_transforms: list[Any] = field(default_factory=list)
    extra_handlers: dict[str, Handler] = field(default_factory=dict)
    checkpoint_enabled: bool = True


@dataclass
class EngineEvent:
    kind: str
    node_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class PipelineEngine:
    """Executes a parsed Graph pipeline."""

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or EngineConfig()
        self._registry = HandlerRegistry()
        self._events: list[EngineEvent] = []
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        interviewer = self.config.interviewer or AutoApproveInterviewer()
        self._registry.register("start", StartHandler())
        self._registry.register("exit", ExitHandler())
        self._registry.register("conditional", ConditionalHandler())
        self._registry.register("codergen", CodergenHandler(backend=self.config.codergen_backend))
        self._registry.register("wait.human", WaitForHumanHandler(interviewer))
        self._registry.register("parallel", ParallelHandler())
        self._registry.register("parallel.fan_in", FanInHandler())
        self._registry.register("tool", ToolHandler())
        self._registry.register("stack.manager_loop", ManagerLoopHandler())
        for type_str, handler in self.config.extra_handlers.items():
            self._registry.register(type_str, handler)

    @property
    def events(self) -> list[EngineEvent]:
        return list(self._events)

    def _emit(self, kind: str, node_id: str = "", **data: Any) -> None:
        self._events.append(EngineEvent(kind=kind, node_id=node_id, data=data))

    async def run(self, graph: Graph, resume_from: Checkpoint | None = None) -> Outcome:
        """Execute the pipeline graph."""
        self._emit("pipeline.start", data={"name": graph.name, "goal": graph.goal})

        # Initialize context
        if resume_from:
            context = resume_from.restore_context()
            completed_nodes = list(resume_from.completed_nodes)
            node_outcomes: dict[str, Outcome] = {}
            node_retries = dict(resume_from.node_retries)
        else:
            context = Context()
            _mirror_graph_attrs(graph, context)
            completed_nodes: list[str] = []
            node_outcomes: dict[str, Outcome] = {}
            node_retries: dict[str, int] = {}

        logs_root = self.config.logs_root or "/tmp/attractor-run"
        os.makedirs(logs_root, exist_ok=True)

        # Find start
        start = graph.start_node()
        if start is None:
            return Outcome(status=StageStatus.FAIL, failure_reason="No start node found")

        if resume_from and resume_from.current_node:
            # Resume: advance past the checkpoint node
            current = graph.get_node(resume_from.current_node)
            if current is None:
                return Outcome(status=StageStatus.FAIL, failure_reason=f"Resume node '{resume_from.current_node}' not found")
            # Find the next edge from the checkpoint node
            edges = graph.outgoing_edges(current.id)
            if edges:
                current = graph.get_node(edges[0].target)
            else:
                current = None
        else:
            current = start

        last_outcome = Outcome(status=StageStatus.SUCCESS)
        steps = 0

        while current is not None and steps < self.config.max_steps:
            steps += 1
            node = current

            # Step 1: Check for terminal node
            if node.handler_type == "exit":
                gate_ok, failed_gate = _check_goal_gates(graph, node_outcomes)
                if not gate_ok and failed_gate:
                    retry_target = _get_retry_target(failed_gate, graph)
                    if retry_target:
                        current = graph.get_node(retry_target)
                        self._emit("goal_gate.retry", node_id=failed_gate.id,
                                   target=retry_target)
                        continue
                    else:
                        self._emit("pipeline.error", node_id=failed_gate.id,
                                   error="Goal gate unsatisfied and no retry target")
                        return Outcome(status=StageStatus.FAIL,
                                       failure_reason=f"Goal gate '{failed_gate.id}' unsatisfied, no retry target")
                self._emit("pipeline.complete", node_id=node.id)
                break

            # Step 2: Execute handler with retry
            self._emit("node.start", node_id=node.id)
            handler = self._registry.resolve(node)

            if self.config.dry_run:
                outcome = Outcome(status=StageStatus.SUCCESS, notes=f"[dry-run] {node.id}")
            else:
                outcome = await _execute_with_retry(
                    handler, node, context, graph, logs_root,
                    node_retries, self._emit,
                )

            last_outcome = outcome
            self._emit("node.complete", node_id=node.id, status=outcome.status.value)

            # Step 3: Record
            completed_nodes.append(node.id)
            node_outcomes[node.id] = outcome

            # Step 4: Apply context updates
            context.apply_updates(outcome.context_updates)
            context.set("outcome", outcome.status.value)
            if outcome.preferred_label:
                context.set("preferred_label", outcome.preferred_label)

            # Step 5: Checkpoint
            if self.config.checkpoint_enabled and logs_root:
                cp = Checkpoint.from_context(context, node.id, completed_nodes, node_retries)
                cp.save(os.path.join(logs_root, "checkpoint.json"))

            # Step 6: Select next edge
            next_edge = select_edge(node, outcome, context, graph)
            if next_edge is None:
                if outcome.status == StageStatus.FAIL:
                    self._emit("pipeline.error", node_id=node.id,
                               error="Stage failed with no outgoing fail edge")
                break

            # Step 7: loop_restart
            if next_edge.loop_restart:
                self._emit("loop.restart", node_id=node.id, target=next_edge.target)
                current = graph.get_node(next_edge.target) or start
                completed_nodes.clear()
                node_outcomes.clear()
                node_retries.clear()
                continue

            # Step 8: Advance
            current = graph.get_node(next_edge.target)

        self._emit("pipeline.finalize")
        return last_outcome

    async def run_dot(self, dot_source: str) -> Outcome:
        """Parse, validate, transform, and execute a DOT source string."""
        graph = parse_dot(dot_source)
        # Apply transforms
        graph = VariableExpansionTransform().apply(graph)
        graph = StylesheetTransform().apply(graph)
        for t in self.config.extra_transforms:
            graph = t.apply(graph)
        # Validate
        validate_or_raise(graph)
        return await self.run(graph)


def select_edge(node: Node, outcome: Outcome, context: Context, graph: Graph) -> Edge | None:
    """5-step edge selection algorithm."""
    edges = graph.outgoing_edges(node.id)
    if not edges:
        return None

    # Step 1: Condition matching
    condition_matched = []
    for edge in edges:
        if edge.condition:
            if evaluate_condition(edge.condition, outcome, context):
                condition_matched.append(edge)
    if condition_matched:
        return _best_by_weight_then_lexical(condition_matched)

    # Step 2: Preferred label
    if outcome.preferred_label:
        norm_pref = _normalize_label(outcome.preferred_label)
        for edge in edges:
            if edge.label and _normalize_label(edge.label) == norm_pref:
                return edge

    # Step 3: Suggested next IDs
    if outcome.suggested_next_ids:
        for suggested in outcome.suggested_next_ids:
            for edge in edges:
                if edge.target == suggested:
                    return edge

    # Step 4 & 5: Weight with lexical tiebreak (unconditional only)
    unconditional = [e for e in edges if not e.condition]
    if unconditional:
        return _best_by_weight_then_lexical(unconditional)

    # Fallback: any edge
    return _best_by_weight_then_lexical(edges)


def _best_by_weight_then_lexical(edges: list[Edge]) -> Edge:
    return sorted(edges, key=lambda e: (-e.weight, e.target))[0]


def _normalize_label(label: str) -> str:
    """Normalize label for comparison: lowercase, strip accelerator prefixes."""
    import re
    label = label.strip().lower()
    # Strip [K] , K) , K - prefixes
    label = re.sub(r"^\[\w\]\s+", "", label)
    label = re.sub(r"^\w\)\s+", "", label)
    label = re.sub(r"^\w\s+-\s+", "", label)
    return label


def _check_goal_gates(graph: Graph, node_outcomes: dict[str, Outcome]) -> tuple[bool, Node | None]:
    for node_id, outcome in node_outcomes.items():
        node = graph.get_node(node_id)
        if node and node.goal_gate:
            if not outcome.is_success:
                return False, node
    return True, None


def _get_retry_target(node: Node, graph: Graph) -> str | None:
    if node.retry_target and node.retry_target in graph.nodes:
        return node.retry_target
    if node.fallback_retry_target and node.fallback_retry_target in graph.nodes:
        return node.fallback_retry_target
    if graph.retry_target and graph.retry_target in graph.nodes:
        return graph.retry_target
    if graph.fallback_retry_target and graph.fallback_retry_target in graph.nodes:
        return graph.fallback_retry_target
    return None


def _mirror_graph_attrs(graph: Graph, context: Context) -> None:
    context.set("pipeline.name", graph.name)
    context.set("pipeline.goal", graph.goal)
    if graph.goal:
        context.set("goal", graph.goal)


async def _execute_with_retry(
    handler: Handler,
    node: Node,
    context: Context,
    graph: Graph,
    logs_root: str,
    node_retries: dict[str, int],
    emit: Any,
) -> Outcome:
    max_retries = node.max_retries or graph.default_max_retry
    max_attempts = max_retries + 1

    for attempt in range(1, max_attempts + 1):
        try:
            outcome = await handler.execute(node, context, graph, logs_root)
        except Exception as e:
            if attempt < max_attempts:
                node_retries[node.id] = node_retries.get(node.id, 0) + 1
                emit("node.retry", node_id=node.id, attempt=attempt, reason=str(e))
                await asyncio.sleep(0.01)  # minimal backoff for testing
                continue
            return Outcome(status=StageStatus.FAIL, failure_reason=str(e))

        if outcome.is_success:
            node_retries.pop(node.id, None)
            return outcome

        if outcome.status == StageStatus.RETRY:
            if attempt < max_attempts:
                node_retries[node.id] = node_retries.get(node.id, 0) + 1
                emit("node.retry", node_id=node.id, attempt=attempt, reason="retry requested")
                await asyncio.sleep(0.01)
                continue
            if node.allow_partial:
                return Outcome(status=StageStatus.PARTIAL_SUCCESS, notes="retries exhausted, partial accepted")
            return Outcome(status=StageStatus.FAIL, failure_reason="max retries exceeded")

        if outcome.status == StageStatus.FAIL:
            return outcome

    return Outcome(status=StageStatus.FAIL, failure_reason="max retries exceeded")
