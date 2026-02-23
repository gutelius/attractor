"""Tests for attractor_llm.retry."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from attractor_llm.retry import RetryPolicy, retry
from attractor_llm.errors import (
    RateLimitError,
    ServerError,
    AuthenticationError,
    NetworkError,
)


class TestRetryPolicy:
    def test_defaults(self):
        policy = RetryPolicy()
        assert policy.max_retries == 2
        assert policy.base_delay == 1.0
        assert policy.max_delay == 60.0
        assert policy.backoff_multiplier == 2.0
        assert policy.jitter is True

    def test_delay_calculation_no_jitter(self):
        policy = RetryPolicy(jitter=False)
        assert policy.calculate_delay(0) == 1.0
        assert policy.calculate_delay(1) == 2.0
        assert policy.calculate_delay(2) == 4.0
        assert policy.calculate_delay(3) == 8.0

    def test_delay_capped_at_max(self):
        policy = RetryPolicy(jitter=False, max_delay=5.0)
        assert policy.calculate_delay(0) == 1.0
        assert policy.calculate_delay(2) == 4.0
        assert policy.calculate_delay(3) == 5.0  # capped
        assert policy.calculate_delay(10) == 5.0  # still capped

    def test_delay_with_jitter_in_range(self):
        policy = RetryPolicy(jitter=True)
        for _ in range(100):
            delay = policy.calculate_delay(0)
            assert 0.5 <= delay <= 1.5  # base=1.0, jitter +/- 50%

    def test_retry_after_override(self):
        policy = RetryPolicy(jitter=False)
        # retry_after < max_delay: use it
        assert policy.calculate_delay(0, retry_after=3.0) == 3.0
        # retry_after > max_delay: returns None (don't retry)
        assert policy.calculate_delay(0, retry_after=100.0) is None


@pytest.mark.asyncio
class TestRetryFunction:
    async def test_succeeds_first_try(self):
        fn = AsyncMock(return_value="ok")
        result = await retry(fn, RetryPolicy())
        assert result == "ok"
        assert fn.call_count == 1

    async def test_retries_on_retryable_error(self):
        fn = AsyncMock(
            side_effect=[
                ServerError("fail", provider="openai"),
                "ok",
            ]
        )
        result = await retry(fn, RetryPolicy(max_retries=2, jitter=False, base_delay=0.01))
        assert result == "ok"
        assert fn.call_count == 2

    async def test_raises_after_max_retries(self):
        err = ServerError("fail", provider="openai")
        fn = AsyncMock(side_effect=err)
        with pytest.raises(ServerError):
            await retry(fn, RetryPolicy(max_retries=2, jitter=False, base_delay=0.01))
        assert fn.call_count == 3  # initial + 2 retries

    async def test_no_retry_on_non_retryable(self):
        fn = AsyncMock(side_effect=AuthenticationError("bad key", provider="openai"))
        with pytest.raises(AuthenticationError):
            await retry(fn, RetryPolicy(max_retries=2))
        assert fn.call_count == 1

    async def test_max_retries_zero_disables(self):
        fn = AsyncMock(side_effect=NetworkError("fail"))
        with pytest.raises(NetworkError):
            await retry(fn, RetryPolicy(max_retries=0))
        assert fn.call_count == 1

    async def test_on_retry_callback(self):
        callback = MagicMock()
        fn = AsyncMock(
            side_effect=[
                ServerError("fail", provider="openai"),
                "ok",
            ]
        )
        policy = RetryPolicy(max_retries=2, jitter=False, base_delay=0.01, on_retry=callback)
        await retry(fn, policy)
        assert callback.call_count == 1
        # callback receives (error, attempt, delay)
        args = callback.call_args[0]
        assert isinstance(args[0], ServerError)
        assert args[1] == 0  # attempt number
        assert isinstance(args[2], float)  # delay

    async def test_retry_after_exceeds_max_delay_raises(self):
        err = RateLimitError("rate limited", provider="openai")
        err.retry_after = 120.0
        fn = AsyncMock(side_effect=err)
        with pytest.raises(RateLimitError):
            await retry(fn, RetryPolicy(max_retries=2, max_delay=60.0, base_delay=0.01))
        assert fn.call_count == 1  # no retry because retry_after > max_delay
