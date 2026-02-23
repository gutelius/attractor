"""Event system for the agent loop."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable


class EventKind(str, Enum):
    SESSION_START = "session_start"
    SESSION_END = "session_end"
    USER_INPUT = "user_input"
    ASSISTANT_TEXT_START = "assistant_text_start"
    ASSISTANT_TEXT_DELTA = "assistant_text_delta"
    ASSISTANT_TEXT_END = "assistant_text_end"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_OUTPUT_DELTA = "tool_call_output_delta"
    TOOL_CALL_END = "tool_call_end"
    STEERING_INJECTED = "steering_injected"
    TURN_LIMIT = "turn_limit"
    LOOP_DETECTION = "loop_detection"
    ERROR = "error"


@dataclass
class SessionEvent:
    kind: EventKind
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    data: dict[str, Any] = field(default_factory=dict)


class EventEmitter:
    """Delivers typed events to subscribers via async queue."""

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[SessionEvent]] = []
        self._callbacks: list[Callable[[SessionEvent], Any]] = []

    def subscribe(self) -> asyncio.Queue[SessionEvent]:
        """Create a new subscription queue."""
        q: asyncio.Queue[SessionEvent] = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, queue: asyncio.Queue[SessionEvent]) -> None:
        """Remove a subscription queue."""
        self._subscribers = [q for q in self._subscribers if q is not q]

    def on_event(self, callback: Callable[[SessionEvent], Any]) -> None:
        """Register a callback for all events."""
        self._callbacks.append(callback)

    async def emit(self, event: SessionEvent) -> None:
        """Emit an event to all subscribers and callbacks."""
        for q in self._subscribers:
            await q.put(event)
        for cb in self._callbacks:
            try:
                result = cb(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass  # Don't let subscriber errors break the loop

    def emit_sync(self, event: SessionEvent) -> None:
        """Non-async emit for use in sync contexts (best-effort)."""
        for cb in self._callbacks:
            try:
                cb(event)
            except Exception:
                pass


def _tool_call_signature(name: str, arguments: dict[str, Any]) -> str:
    """Create a signature hash for a tool call."""
    key = json.dumps({"name": name, "args": arguments}, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()


def detect_loop(
    signatures: list[str],
    window_size: int = 10,
) -> bool:
    """Detect repeating patterns in recent tool call signatures.

    Checks for repeating patterns of length 1, 2, or 3 within
    the last `window_size` calls.
    """
    if len(signatures) < window_size:
        return False

    recent = signatures[-window_size:]

    for pattern_len in (1, 2, 3):
        if window_size % pattern_len != 0:
            continue
        pattern = recent[:pattern_len]
        all_match = True
        for i in range(pattern_len, window_size, pattern_len):
            if recent[i : i + pattern_len] != pattern:
                all_match = False
                break
        if all_match:
            return True

    return False


class SteeringQueue:
    """Thread-safe queue for injecting steering messages."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def enqueue(self, message: str) -> None:
        await self._queue.put(message)

    def enqueue_sync(self, message: str) -> None:
        self._queue.put_nowait(message)

    async def drain(self) -> list[str]:
        """Drain all pending messages."""
        messages: list[str] = []
        while not self._queue.empty():
            try:
                messages.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return messages

    @property
    def empty(self) -> bool:
        return self._queue.empty()


class FollowUpQueue:
    """Queue for messages to process after the current input completes."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()

    async def enqueue(self, message: str) -> None:
        await self._queue.put(message)

    async def dequeue(self) -> str | None:
        if self._queue.empty():
            return None
        return self._queue.get_nowait()

    @property
    def empty(self) -> bool:
        return self._queue.empty()
