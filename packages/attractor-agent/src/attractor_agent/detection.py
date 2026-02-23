"""Loop detection utilities."""

from __future__ import annotations

from attractor_agent.events import _tool_call_signature, detect_loop


__all__ = ["detect_loop", "tool_call_signature"]


def tool_call_signature(name: str, arguments: dict) -> str:
    """Create a signature for a tool call (name + arguments hash)."""
    return _tool_call_signature(name, arguments)
