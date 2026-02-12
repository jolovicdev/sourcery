from __future__ import annotations

from collections.abc import Sequence

from sourcery.exceptions import ErrorContext, SourceryProviderError, SourceryRateLimitError

_RATE_LIMIT_MARKERS = (
    "rate limit",
    "too many requests",
    "429",
    "quota",
)

_TRANSIENT_MARKERS = (
    "timeout",
    "temporarily unavailable",
    "service unavailable",
    "internal server error",
    "connection reset",
    "connection aborted",
    "connection error",
    "gateway timeout",
    "bad gateway",
    "503",
    "502",
)


def _normalize(message: str) -> str:
    return message.strip().lower()


def is_rate_limit_message(message: str) -> bool:
    normalized = _normalize(message)
    return any(marker in normalized for marker in _RATE_LIMIT_MARKERS)


def is_transient_message(message: str) -> bool:
    normalized = _normalize(message)
    return any(marker in normalized for marker in _TRANSIENT_MARKERS)


def classify_provider_errors(
    errors: Sequence[str],
    *,
    context: ErrorContext | None = None,
) -> SourceryProviderError:
    if any(is_rate_limit_message(error) for error in errors):
        return SourceryRateLimitError("; ".join(errors), context=context)
    return SourceryProviderError("; ".join(errors), context=context)
