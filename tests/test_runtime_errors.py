from __future__ import annotations

from sourcery.exceptions import SourceryProviderError, SourceryRateLimitError
from sourcery.runtime.errors import (
    classify_provider_errors,
    is_rate_limit_message,
    is_transient_message,
)


def test_detects_rate_limit_message() -> None:
    assert is_rate_limit_message("429 Too Many Requests")


def test_detects_transient_message() -> None:
    assert is_transient_message("Service unavailable")


def test_classifies_rate_limit_error() -> None:
    error = classify_provider_errors(["rate limit exceeded"])
    assert isinstance(error, SourceryRateLimitError)


def test_classifies_generic_provider_error() -> None:
    error = classify_provider_errors(["schema mismatch"])
    assert isinstance(error, SourceryProviderError)
