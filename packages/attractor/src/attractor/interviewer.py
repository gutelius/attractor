"""Interviewer protocol and implementations for human-in-the-loop."""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol


class QuestionType(Enum):
    YES_NO = "yes_no"
    MULTIPLE_CHOICE = "multiple_choice"
    FREEFORM = "freeform"
    CONFIRMATION = "confirmation"


class AnswerValue(Enum):
    YES = "yes"
    NO = "no"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"


@dataclass
class Option:
    key: str
    label: str


@dataclass
class Question:
    text: str
    type: QuestionType = QuestionType.MULTIPLE_CHOICE
    options: list[Option] = field(default_factory=list)
    default: Answer | None = None
    timeout_seconds: float | None = None
    stage: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Answer:
    value: str | AnswerValue = ""
    selected_option: Option | None = None
    text: str = ""


def parse_accelerator_key(label: str) -> str:
    """Extract accelerator key from label patterns like [K] Label, K) Label, K - Label."""
    # [K] Label
    m = re.match(r"\[(\w)\]\s+", label)
    if m:
        return m.group(1).upper()
    # K) Label
    m = re.match(r"(\w)\)\s+", label)
    if m:
        return m.group(1).upper()
    # K - Label
    m = re.match(r"(\w)\s+-\s+", label)
    if m:
        return m.group(1).upper()
    # First character
    if label:
        return label[0].upper()
    return ""


class Interviewer(Protocol):
    """Interface for human interaction."""

    async def ask(self, question: Question) -> Answer: ...
    async def ask_multiple(self, questions: list[Question]) -> list[Answer]: ...
    async def inform(self, message: str, stage: str) -> None: ...


class AutoApproveInterviewer:
    """Always approves — for testing and CI/CD."""

    async def ask(self, question: Question) -> Answer:
        if question.type in (QuestionType.YES_NO, QuestionType.CONFIRMATION):
            return Answer(value=AnswerValue.YES)
        if question.type == QuestionType.MULTIPLE_CHOICE and question.options:
            return Answer(value=question.options[0].key, selected_option=question.options[0])
        return Answer(value="auto-approved", text="auto-approved")

    async def ask_multiple(self, questions: list[Question]) -> list[Answer]:
        return [await self.ask(q) for q in questions]

    async def inform(self, message: str, stage: str) -> None:
        pass


class QueueInterviewer:
    """Reads from a pre-filled answer queue — for deterministic testing."""

    def __init__(self, answers: list[Answer] | None = None) -> None:
        self._answers: deque[Answer] = deque(answers or [])

    def enqueue(self, answer: Answer) -> None:
        self._answers.append(answer)

    async def ask(self, question: Question) -> Answer:
        if self._answers:
            return self._answers.popleft()
        return Answer(value=AnswerValue.SKIPPED)

    async def ask_multiple(self, questions: list[Question]) -> list[Answer]:
        return [await self.ask(q) for q in questions]

    async def inform(self, message: str, stage: str) -> None:
        pass


class CallbackInterviewer:
    """Delegates to a callback function."""

    def __init__(self, callback: Callable[[Question], Answer]) -> None:
        self._callback = callback

    async def ask(self, question: Question) -> Answer:
        return self._callback(question)

    async def ask_multiple(self, questions: list[Question]) -> list[Answer]:
        return [self._callback(q) for q in questions]

    async def inform(self, message: str, stage: str) -> None:
        pass


class RecordingInterviewer:
    """Wraps another interviewer and records interactions."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.recordings: list[tuple[Question, Answer]] = []

    async def ask(self, question: Question) -> Answer:
        answer = await self.inner.ask(question)
        self.recordings.append((question, answer))
        return answer

    async def ask_multiple(self, questions: list[Question]) -> list[Answer]:
        answers = await self.inner.ask_multiple(questions)
        for q, a in zip(questions, answers):
            self.recordings.append((q, a))
        return answers

    async def inform(self, message: str, stage: str) -> None:
        await self.inner.inform(message, stage)
