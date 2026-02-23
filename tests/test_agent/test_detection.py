"""Tests for loop detection module."""

from attractor_agent.detection import detect_loop, tool_call_signature


class TestDetectionModule:
    def test_detect_loop_reexport(self):
        sigs = ["a"] * 10
        assert detect_loop(sigs, window_size=10)

    def test_tool_call_signature_reexport(self):
        sig = tool_call_signature("read_file", {"path": "/tmp/test"})
        assert isinstance(sig, str)
        assert len(sig) > 0
