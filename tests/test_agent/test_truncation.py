"""Tests for output truncation."""

import pytest

from attractor_agent.tools.truncation import (
    truncate_chars,
    truncate_lines,
    truncate_output,
    TruncationResult,
)


class TestTruncateChars:
    def test_fits_without_truncation(self):
        assert truncate_chars("hello", 100) == "hello"

    def test_head_tail_mode(self):
        text = "a" * 100
        result = truncate_chars(text, 20)
        assert "truncated" in result
        assert len(result) < 100

    def test_tail_mode(self):
        text = "START" + "x" * 100 + "END"
        result = truncate_chars(text, 20, mode="tail")
        assert result.endswith("END")
        assert "truncated" in result

    def test_empty_string(self):
        assert truncate_chars("", 100) == ""

    def test_exact_limit(self):
        text = "a" * 50
        assert truncate_chars(text, 50) == text


class TestTruncateLines:
    def test_fits_without_truncation(self):
        text = "a\nb\nc\n"
        assert truncate_lines(text, 10) == text

    def test_truncates_middle(self):
        lines = [f"line{i}\n" for i in range(100)]
        text = "".join(lines)
        result = truncate_lines(text, 10)
        assert "truncated" in result
        assert "line0" in result  # head preserved
        assert "line99" in result  # tail preserved

    def test_single_line(self):
        assert truncate_lines("hello", 5) == "hello"

    def test_empty(self):
        assert truncate_lines("", 5) == ""


class TestTruncateOutput:
    def test_no_truncation_needed(self):
        result = truncate_output("hello", "shell")
        assert not result.was_truncated
        assert result.text == "hello"

    def test_char_truncation_applied(self):
        text = "x" * 50_000
        result = truncate_output(text, "shell")  # 30K char limit
        assert result.was_truncated
        assert len(result.text) < 50_000

    def test_line_truncation_applied(self):
        lines = "line\n" * 500
        result = truncate_output(lines, "shell")  # 256 line limit
        assert result.was_truncated

    def test_custom_limits(self):
        text = "x" * 100
        result = truncate_output(text, "unknown", char_limit=50)
        assert result.was_truncated

    def test_original_counts(self):
        text = "line1\nline2\nline3\n"
        result = truncate_output(text, "shell")
        assert result.original_chars == len(text)
        assert result.original_lines == 3

    def test_tool_specific_limits(self):
        # read_file has 50K char limit
        text = "x" * 40_000
        result = truncate_output(text, "read_file")
        assert not result.was_truncated  # under 50K

        # write_file has 1K char limit
        text = "x" * 2_000
        result = truncate_output(text, "write_file")
        assert result.was_truncated

    def test_char_before_line(self):
        # Char truncation happens first, reducing line count
        text = ("x" * 1000 + "\n") * 300  # 300 lines, ~300K chars
        result = truncate_output(text, "grep")  # 20K chars, 200 lines
        assert result.was_truncated
