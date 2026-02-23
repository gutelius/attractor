"""Codergen handler — LLM task execution."""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

from attractor.context import Context
from attractor.graph import Graph, Node
from attractor.outcome import Outcome, StageStatus


class CodergenBackend(Protocol):
    """Interface for LLM execution backends."""

    async def run(self, node: Node, prompt: str, context: Context) -> str | Outcome: ...


def expand_variables(text: str, graph: Graph, context: Context) -> str:
    """Expand template variables in prompt text."""
    result = text.replace("$goal", graph.goal)
    return result


def _write_status(stage_dir: str, outcome: Outcome) -> None:
    """Write status.json for audit trail."""
    data = {
        "status": outcome.status.value,
        "notes": outcome.notes,
        "failure_reason": outcome.failure_reason,
        "context_updates": outcome.context_updates,
    }
    with open(os.path.join(stage_dir, "status.json"), "w") as f:
        json.dump(data, f, indent=2)


class CodergenHandler:
    """Default handler for LLM task nodes."""

    def __init__(self, backend: CodergenBackend | None = None) -> None:
        self.backend = backend

    async def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        # 1. Build prompt
        prompt = node.prompt or node.label
        prompt = expand_variables(prompt, graph, context)

        # 2. Write prompt to logs
        stage_dir = os.path.join(logs_root, node.id)
        os.makedirs(stage_dir, exist_ok=True)
        with open(os.path.join(stage_dir, "prompt.md"), "w") as f:
            f.write(prompt)

        # 3. Call LLM backend
        if self.backend is not None:
            try:
                result = await self.backend.run(node, prompt, context)
                if isinstance(result, Outcome):
                    _write_status(stage_dir, result)
                    return result
                response_text = str(result)
            except Exception as e:
                outcome = Outcome(status=StageStatus.FAIL, failure_reason=str(e))
                _write_status(stage_dir, outcome)
                return outcome
        else:
            response_text = f"[Simulated] Response for stage: {node.id}"

        # 4. Write response to logs
        with open(os.path.join(stage_dir, "response.md"), "w") as f:
            f.write(response_text)

        # 5. Return outcome
        outcome = Outcome(
            status=StageStatus.SUCCESS,
            notes=f"Stage completed: {node.id}",
            context_updates={
                "last_stage": node.id,
                "last_response": response_text[:200],
            },
        )
        _write_status(stage_dir, outcome)
        return outcome
