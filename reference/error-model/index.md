# Error Model

Exceptions are defined in `sourcery/exceptions.py`.

## Base Class

- `SourceryError`

Catch this only at process boundaries where generic Sourcery failure handling is acceptable.

## Runtime and Provider

- `SourceryRuntimeError`
- `SourceryProviderError`
- `SourceryRateLimitError`
- `SourceryPausedRunError`
- `SourceryRetryExhaustedError`
- `RuntimeIntegrationError`

Runtime/provider exceptions may include `exc.context` (`run_id`, `pass_id`, `chunk_id`, `model`, `provider`).

`SourceryRetryExhaustedError` includes `.attempts`.

## Pipeline

- `SourceryPipelineError`
- `ExampleValidationError`

Use these to distinguish deterministic task/schema/pipeline problems from runtime/provider failures.

## Ingestion

- `SourceryIngestionError`
- `SourceryDependencyError`

Dependency errors indicate missing optional packages (`pypdf`, `Pillow`, `pytesseract`).

## Runtime Classification Behavior

`runtime/errors.py` classifies provider error text into:

- rate-limit markers (`429`, `rate limit`, `too many requests`, `quota`),
- transient markers (`timeout`, `503`, `502`, `connection reset`, etc.).

This classification drives retry decisions in BlackGeorge runtime mixins.

## Recommended Handling Pattern

```
import sourcery

from sourcery.exceptions import (
    ExampleValidationError,
    SourceryDependencyError,
    SourceryRateLimitError,
    SourceryRetryExhaustedError,
    SourceryRuntimeError,
)

try:
    result = sourcery.extract(request)
except ExampleValidationError as exc:
    print("Fix task examples:", exc)
except SourceryDependencyError as exc:
    print("Install missing optional dependency:", exc)
except SourceryRateLimitError as exc:
    print("Provider rate limited request:", exc)
except SourceryRetryExhaustedError as exc:
    print("Retry policy exhausted after", exc.attempts, "attempts")
except SourceryRuntimeError as exc:
    print("Runtime failure:", exc, "context:", exc.context)
```
