"""Tests for attractor_llm.errors."""

import pytest
from attractor_llm.errors import (
    SDKError,
    ProviderError,
    AuthenticationError,
    AccessDeniedError,
    NotFoundError,
    InvalidRequestError,
    RateLimitError,
    ServerError,
    ContentFilterError,
    ContextLengthError,
    QuotaExceededError,
    RequestTimeoutError,
    AbortError,
    NetworkError,
    StreamError,
    InvalidToolCallError,
    NoObjectGeneratedError,
    ConfigurationError,
    classify_error_message,
)


class TestErrorHierarchy:
    def test_all_inherit_from_sdk_error(self):
        errors = [
            ProviderError("test", provider="openai"),
            AuthenticationError("test", provider="openai"),
            RequestTimeoutError("test"),
            AbortError("test"),
            NetworkError("test"),
            StreamError("test"),
            InvalidToolCallError("test"),
            NoObjectGeneratedError("test"),
            ConfigurationError("test"),
        ]
        for err in errors:
            assert isinstance(err, SDKError)

    def test_provider_subclasses(self):
        subclasses = [
            AuthenticationError("test", provider="openai"),
            AccessDeniedError("test", provider="openai"),
            NotFoundError("test", provider="openai"),
            InvalidRequestError("test", provider="openai"),
            RateLimitError("test", provider="openai"),
            ServerError("test", provider="openai"),
            ContentFilterError("test", provider="openai"),
            ContextLengthError("test", provider="openai"),
            QuotaExceededError("test", provider="openai"),
        ]
        for err in subclasses:
            assert isinstance(err, ProviderError)
            assert isinstance(err, SDKError)


class TestRetryable:
    def test_non_retryable(self):
        assert not AuthenticationError("test", provider="x").retryable
        assert not AccessDeniedError("test", provider="x").retryable
        assert not NotFoundError("test", provider="x").retryable
        assert not InvalidRequestError("test", provider="x").retryable
        assert not ContextLengthError("test", provider="x").retryable
        assert not QuotaExceededError("test", provider="x").retryable
        assert not ContentFilterError("test", provider="x").retryable
        assert not ConfigurationError("test").retryable
        assert not AbortError("test").retryable
        assert not InvalidToolCallError("test").retryable
        assert not NoObjectGeneratedError("test").retryable

    def test_retryable(self):
        assert RateLimitError("test", provider="x").retryable
        assert ServerError("test", provider="x").retryable
        assert RequestTimeoutError("test").retryable
        assert NetworkError("test").retryable
        assert StreamError("test").retryable


class TestProviderErrorFields:
    def test_fields(self):
        err = ProviderError(
            "something went wrong",
            provider="openai",
            status_code=500,
            error_code="internal_error",
            retry_after=5.0,
            raw={"error": {"message": "internal"}},
        )
        assert err.provider == "openai"
        assert err.status_code == 500
        assert err.error_code == "internal_error"
        assert err.retry_after == 5.0
        assert err.raw == {"error": {"message": "internal"}}
        assert str(err) == "something went wrong"

    def test_cause(self):
        cause = ValueError("original")
        err = SDKError("wrapped", cause=cause)
        assert err.cause is cause


class TestClassifyErrorMessage:
    def test_not_found(self):
        assert classify_error_message("model not found") == "not_found"
        assert classify_error_message("resource does not exist") == "not_found"

    def test_auth(self):
        assert classify_error_message("unauthorized access") == "authentication"
        assert classify_error_message("invalid key provided") == "authentication"

    def test_context_length(self):
        assert classify_error_message("context length exceeded") == "context_length"
        assert classify_error_message("too many tokens in request") == "context_length"

    def test_content_filter(self):
        assert classify_error_message("content filter triggered") == "content_filter"
        assert classify_error_message("blocked by safety system") == "content_filter"

    def test_unknown(self):
        assert classify_error_message("something random") is None
