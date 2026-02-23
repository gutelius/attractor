"""Retry policy with exponential backoff and jitter."""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypeVar

from attractor_llm.errors import SDKError

T = TypeVar("T")


@dataclass
class RetryPolicy:
    max_retries: int = 2
    base_delay: float = 1.0
    max_delay: float = 60.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    on_retry: Callable[[Exception, int, float], Any] | None = None

    def calculate_delay(
        self, attempt: int, *, retry_after: float | None = None
    ) -> float | None:
        """Calculate delay for a given attempt.

        Returns None if retry_after exceeds max_delay (caller should not retry).
        """
        if retry_after is not None:
            if retry_after > self.max_delay:
                return None
            return retry_after

        delay = min(
            self.base_delay * (self.backoff_multiplier ** attempt),
            self.max_delay,
        )
        if self.jitter:
            delay *= random.uniform(0.5, 1.5)
        return delay


async def retry(
    fn: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
) -> T:
    """Execute fn with retry according to policy."""
    last_error: Exception | None = None

    for attempt in range(policy.max_retries + 1):
        try:
            return await fn()
        except SDKError as err:
            last_error = err
            if not err.retryable:
                raise

            if attempt >= policy.max_retries:
                raise

            retry_after = getattr(err, "retry_after", None)
            delay = policy.calculate_delay(attempt, retry_after=retry_after)

            if delay is None:
                raise

            if policy.on_retry:
                policy.on_retry(err, attempt, delay)

            await asyncio.sleep(delay)

    raise last_error  # type: ignore[misc]
