from __future__ import annotations

from dataclasses import dataclass


class SourceryError(Exception):
    pass


@dataclass(slots=True, frozen=True)
class ErrorContext:
    run_id: str | None = None
    pass_id: int | None = None
    chunk_id: str | None = None
    model: str | None = None
    provider: str | None = None


class SourceryRuntimeError(SourceryError):
    def __init__(self, message: str, *, context: ErrorContext | None = None) -> None:
        super().__init__(message)
        self.context = context


class SourceryProviderError(SourceryRuntimeError):
    pass


class SourceryRateLimitError(SourceryProviderError):
    pass


class SourceryPausedRunError(SourceryRuntimeError):
    pass


class SourceryRetryExhaustedError(SourceryProviderError):
    def __init__(
        self,
        message: str,
        *,
        attempts: int,
        context: ErrorContext | None = None,
    ) -> None:
        super().__init__(message, context=context)
        self.attempts = attempts


class SourceryPipelineError(SourceryError):
    pass


class RuntimeIntegrationError(SourceryRuntimeError):
    pass


class ExampleValidationError(SourceryPipelineError):
    pass


class SourceryIngestionError(SourceryError):
    pass


class SourceryDependencyError(SourceryIngestionError):
    pass
