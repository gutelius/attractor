"""Error hierarchy for the unified LLM client."""

from __future__ import annotations

from typing import Any


class SDKError(Exception):
    """Base error for all library errors."""

    def __init__(self, message: str, *, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause

    @property
    def retryable(self) -> bool:
        return False


class ProviderError(SDKError):
    """Error returned by an LLM provider."""

    def __init__(
        self,
        message: str,
        *,
        provider: str,
        status_code: int | None = None,
        error_code: str | None = None,
        retryable: bool = True,
        retry_after: float | None = None,
        raw: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ):
        super().__init__(message, cause=cause)
        self.provider = provider
        self.status_code = status_code
        self.error_code = error_code
        self._retryable = retryable
        self.retry_after = retry_after
        self.raw = raw

    @property
    def retryable(self) -> bool:
        return self._retryable


# Non-retryable provider errors

class AuthenticationError(ProviderError):
    def __init__(self, message: str, *, provider: str, **kwargs: Any):
        super().__init__(message, provider=provider, retryable=False, status_code=401, **kwargs)


class AccessDeniedError(ProviderError):
    def __init__(self, message: str, *, provider: str, **kwargs: Any):
        super().__init__(message, provider=provider, retryable=False, status_code=403, **kwargs)


class NotFoundError(ProviderError):
    def __init__(self, message: str, *, provider: str, **kwargs: Any):
        super().__init__(message, provider=provider, retryable=False, status_code=404, **kwargs)


class InvalidRequestError(ProviderError):
    def __init__(self, message: str, *, provider: str, **kwargs: Any):
        super().__init__(message, provider=provider, retryable=False, status_code=400, **kwargs)


class ContentFilterError(ProviderError):
    def __init__(self, message: str, *, provider: str, **kwargs: Any):
        super().__init__(message, provider=provider, retryable=False, **kwargs)


class ContextLengthError(ProviderError):
    def __init__(self, message: str, *, provider: str, **kwargs: Any):
        super().__init__(message, provider=provider, retryable=False, status_code=413, **kwargs)


class QuotaExceededError(ProviderError):
    def __init__(self, message: str, *, provider: str, **kwargs: Any):
        super().__init__(message, provider=provider, retryable=False, **kwargs)


# Retryable provider errors

class RateLimitError(ProviderError):
    def __init__(self, message: str, *, provider: str, **kwargs: Any):
        super().__init__(message, provider=provider, retryable=True, status_code=429, **kwargs)


class ServerError(ProviderError):
    def __init__(self, message: str, *, provider: str, **kwargs: Any):
        super().__init__(message, provider=provider, retryable=True, **kwargs)


# Non-provider errors

class RequestTimeoutError(SDKError):
    @property
    def retryable(self) -> bool:
        return True


class AbortError(SDKError):
    pass


class NetworkError(SDKError):
    @property
    def retryable(self) -> bool:
        return True


class StreamError(SDKError):
    @property
    def retryable(self) -> bool:
        return True


class InvalidToolCallError(SDKError):
    pass


class NoObjectGeneratedError(SDKError):
    pass


class ConfigurationError(SDKError):
    pass


def classify_error_message(message: str) -> str | None:
    """Classify an error message for ambiguous HTTP status codes."""
    msg = message.lower()
    if "not found" in msg or "does not exist" in msg:
        return "not_found"
    if "unauthorized" in msg or "invalid key" in msg:
        return "authentication"
    if "context length" in msg or "too many tokens" in msg:
        return "context_length"
    if "content filter" in msg or "safety" in msg:
        return "content_filter"
    return None
