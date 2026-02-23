"""Tests for Interviewer implementations."""

import pytest

from attractor.interviewer import (
    Answer,
    AnswerValue,
    AutoApproveInterviewer,
    CallbackInterviewer,
    Option,
    Question,
    QuestionType,
    QueueInterviewer,
    RecordingInterviewer,
    parse_accelerator_key,
)


class TestParseAcceleratorKey:
    def test_bracket_pattern(self):
        assert parse_accelerator_key("[Y] Yes, deploy") == "Y"
        assert parse_accelerator_key("[N] No, cancel") == "N"

    def test_paren_pattern(self):
        assert parse_accelerator_key("Y) Yes, deploy") == "Y"

    def test_dash_pattern(self):
        assert parse_accelerator_key("Y - Yes, deploy") == "Y"

    def test_first_char_fallback(self):
        assert parse_accelerator_key("Yes, deploy") == "Y"
        assert parse_accelerator_key("approve") == "A"

    def test_empty(self):
        assert parse_accelerator_key("") == ""


class TestAutoApproveInterviewer:
    @pytest.mark.asyncio
    async def test_yes_no(self):
        iv = AutoApproveInterviewer()
        ans = await iv.ask(Question(text="Continue?", type=QuestionType.YES_NO))
        assert ans.value == AnswerValue.YES

    @pytest.mark.asyncio
    async def test_confirmation(self):
        iv = AutoApproveInterviewer()
        ans = await iv.ask(Question(text="Confirm?", type=QuestionType.CONFIRMATION))
        assert ans.value == AnswerValue.YES

    @pytest.mark.asyncio
    async def test_multiple_choice(self):
        iv = AutoApproveInterviewer()
        opts = [Option(key="A", label="Option A"), Option(key="B", label="Option B")]
        ans = await iv.ask(Question(text="Pick", type=QuestionType.MULTIPLE_CHOICE, options=opts))
        assert ans.value == "A"
        assert ans.selected_option.label == "Option A"

    @pytest.mark.asyncio
    async def test_freeform(self):
        iv = AutoApproveInterviewer()
        ans = await iv.ask(Question(text="Input?", type=QuestionType.FREEFORM))
        assert ans.text == "auto-approved"


class TestQueueInterviewer:
    @pytest.mark.asyncio
    async def test_dequeues_in_order(self):
        iv = QueueInterviewer([
            Answer(value="first"),
            Answer(value="second"),
        ])
        a1 = await iv.ask(Question(text="Q1"))
        a2 = await iv.ask(Question(text="Q2"))
        assert a1.value == "first"
        assert a2.value == "second"

    @pytest.mark.asyncio
    async def test_empty_queue_returns_skipped(self):
        iv = QueueInterviewer()
        ans = await iv.ask(Question(text="Q"))
        assert ans.value == AnswerValue.SKIPPED

    @pytest.mark.asyncio
    async def test_enqueue(self):
        iv = QueueInterviewer()
        iv.enqueue(Answer(value="added"))
        ans = await iv.ask(Question(text="Q"))
        assert ans.value == "added"


class TestCallbackInterviewer:
    @pytest.mark.asyncio
    async def test_delegates(self):
        def cb(q):
            return Answer(value=f"answer-{q.stage}")
        iv = CallbackInterviewer(cb)
        ans = await iv.ask(Question(text="Q", stage="s1"))
        assert ans.value == "answer-s1"


class TestRecordingInterviewer:
    @pytest.mark.asyncio
    async def test_records_interactions(self):
        inner = AutoApproveInterviewer()
        recorder = RecordingInterviewer(inner)
        q = Question(text="Continue?", type=QuestionType.YES_NO)
        await recorder.ask(q)
        assert len(recorder.recordings) == 1
        assert recorder.recordings[0][0] is q
        assert recorder.recordings[0][1].value == AnswerValue.YES

    @pytest.mark.asyncio
    async def test_records_multiple(self):
        inner = AutoApproveInterviewer()
        recorder = RecordingInterviewer(inner)
        qs = [
            Question(text="Q1", type=QuestionType.YES_NO),
            Question(text="Q2", type=QuestionType.YES_NO),
        ]
        await recorder.ask_multiple(qs)
        assert len(recorder.recordings) == 2
