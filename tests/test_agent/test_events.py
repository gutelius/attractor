"""Tests for event system."""

import asyncio

import pytest

from attractor_agent.events import (
    EventEmitter,
    EventKind,
    SessionEvent,
    SteeringQueue,
    FollowUpQueue,
    detect_loop,
    _tool_call_signature,
)


class TestSessionEvent:
    def test_creation(self):
        e = SessionEvent(kind=EventKind.SESSION_START, session_id="s1")
        assert e.kind == EventKind.SESSION_START
        assert e.session_id == "s1"
        assert e.timestamp > 0

    def test_all_event_kinds(self):
        assert len(EventKind) == 13


class TestEventEmitter:
    async def test_subscribe_receives_events(self):
        emitter = EventEmitter()
        q = emitter.subscribe()
        event = SessionEvent(kind=EventKind.SESSION_START, session_id="s1")
        await emitter.emit(event)
        received = await q.get()
        assert received.kind == EventKind.SESSION_START

    async def test_callback(self):
        emitter = EventEmitter()
        received = []
        emitter.on_event(lambda e: received.append(e))
        await emitter.emit(SessionEvent(kind=EventKind.USER_INPUT))
        assert len(received) == 1
        assert received[0].kind == EventKind.USER_INPUT

    async def test_async_callback(self):
        emitter = EventEmitter()
        received = []

        async def handler(e):
            received.append(e)

        emitter.on_event(handler)
        await emitter.emit(SessionEvent(kind=EventKind.ERROR))
        assert len(received) == 1

    async def test_multiple_subscribers(self):
        emitter = EventEmitter()
        q1 = emitter.subscribe()
        q2 = emitter.subscribe()
        await emitter.emit(SessionEvent(kind=EventKind.SESSION_END))
        assert not q1.empty()
        assert not q2.empty()

    async def test_callback_error_doesnt_break(self):
        emitter = EventEmitter()
        emitter.on_event(lambda e: 1 / 0)  # Will raise
        received = []
        emitter.on_event(lambda e: received.append(e))
        await emitter.emit(SessionEvent(kind=EventKind.ASSISTANT_TEXT_START))
        assert len(received) == 1  # Second callback still ran


class TestDetectLoop:
    def test_no_loop_with_varied_calls(self):
        sigs = [f"sig{i}" for i in range(10)]
        assert not detect_loop(sigs, window_size=10)

    def test_detects_single_repeated_call(self):
        sigs = ["same"] * 10
        assert detect_loop(sigs, window_size=10)

    def test_detects_two_call_cycle(self):
        sigs = ["a", "b"] * 5
        assert detect_loop(sigs, window_size=10)

    def test_detects_three_call_cycle(self):
        sigs = ["a", "b", "c"] * 4
        assert detect_loop(sigs, window_size=12)

    def test_too_few_calls(self):
        sigs = ["a", "b"]
        assert not detect_loop(sigs, window_size=10)

    def test_broken_pattern(self):
        sigs = ["a", "b", "a", "b", "a", "b", "a", "b", "a", "c"]
        assert not detect_loop(sigs, window_size=10)


class TestToolCallSignature:
    def test_same_call_same_sig(self):
        s1 = _tool_call_signature("read", {"path": "/a"})
        s2 = _tool_call_signature("read", {"path": "/a"})
        assert s1 == s2

    def test_different_call_different_sig(self):
        s1 = _tool_call_signature("read", {"path": "/a"})
        s2 = _tool_call_signature("read", {"path": "/b"})
        assert s1 != s2


class TestSteeringQueue:
    async def test_enqueue_drain(self):
        q = SteeringQueue()
        await q.enqueue("msg1")
        await q.enqueue("msg2")
        messages = await q.drain()
        assert messages == ["msg1", "msg2"]
        assert q.empty

    async def test_drain_empty(self):
        q = SteeringQueue()
        messages = await q.drain()
        assert messages == []

    def test_sync_enqueue(self):
        q = SteeringQueue()
        q.enqueue_sync("sync msg")
        assert not q.empty


class TestFollowUpQueue:
    async def test_enqueue_dequeue(self):
        q = FollowUpQueue()
        await q.enqueue("follow up")
        msg = await q.dequeue()
        assert msg == "follow up"

    async def test_dequeue_empty(self):
        q = FollowUpQueue()
        msg = await q.dequeue()
        assert msg is None
