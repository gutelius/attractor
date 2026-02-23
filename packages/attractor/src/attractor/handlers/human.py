"""Wait-for-human handler."""

from __future__ import annotations

from attractor.context import Context
from attractor.graph import Graph, Node
from attractor.interviewer import (
    Answer,
    AnswerValue,
    Interviewer,
    Option,
    Question,
    QuestionType,
    parse_accelerator_key,
)
from attractor.outcome import Outcome, StageStatus


class WaitForHumanHandler:
    """Blocks until a human selects an option from outgoing edges."""

    def __init__(self, interviewer: Interviewer) -> None:
        self.interviewer = interviewer

    async def execute(self, node: Node, context: Context, graph: Graph, logs_root: str) -> Outcome:
        # 1. Derive choices from outgoing edges
        edges = graph.outgoing_edges(node.id)
        if not edges:
            return Outcome(status=StageStatus.FAIL, failure_reason="No outgoing edges for human gate")

        choices: list[tuple[str, str, str]] = []  # (key, label, target_node)
        options: list[Option] = []
        for edge in edges:
            label = edge.label or edge.target
            key = parse_accelerator_key(label)
            choices.append((key, label, edge.target))
            options.append(Option(key=key, label=label))

        # 2. Build question
        question = Question(
            text=node.label or "Select an option:",
            type=QuestionType.MULTIPLE_CHOICE,
            options=options,
            stage=node.id,
        )

        # 3. Ask and wait
        answer = await self.interviewer.ask(question)

        # 4. Handle timeout/skip
        if isinstance(answer.value, AnswerValue):
            if answer.value == AnswerValue.TIMEOUT:
                default_choice = node.extra.get("human.default_choice")
                if default_choice:
                    # Find matching choice
                    for key, label, target in choices:
                        if key == default_choice or label == default_choice:
                            return Outcome(
                                status=StageStatus.SUCCESS,
                                suggested_next_ids=[target],
                                context_updates={"human.gate.selected": key, "human.gate.label": label},
                            )
                return Outcome(status=StageStatus.RETRY, failure_reason="human gate timeout, no default")

            if answer.value == AnswerValue.SKIPPED:
                return Outcome(status=StageStatus.FAIL, failure_reason="human skipped interaction")

        # 5. Find matching choice
        answer_val = str(answer.value)
        selected = None
        for key, label, target in choices:
            if answer_val.upper() == key.upper() or answer_val == label:
                selected = (key, label, target)
                break
        if selected is None:
            selected = choices[0]  # fallback to first

        key, label, target = selected
        return Outcome(
            status=StageStatus.SUCCESS,
            suggested_next_ids=[target],
            context_updates={"human.gate.selected": key, "human.gate.label": label},
        )
