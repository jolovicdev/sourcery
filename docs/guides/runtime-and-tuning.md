# Runtime And Tuning

Use `RuntimeConfig` for provider/runtime behavior and `ExtractOptions` for deterministic pipeline controls.

## RuntimeConfig

Required:

- `model: str`

Common:

- `temperature`
- `max_tokens`
- `stream`
- `storage_dir`
- `respect_context_window`

Retry policy (`retry`):

- `max_attempts`
- `initial_backoff_seconds`
- `max_backoff_seconds`
- `backoff_multiplier`
- `retry_on_rate_limit`
- `retry_on_transient_errors`
- `auto_resume_paused_runs`
- `max_pause_resumes`

Optional workflows:

- `session_refinement`: per-document session context across chunks
- `reconciliation`: canonical claims per document

## ExtractOptions

- `max_chunk_chars`
- `context_window_chars`
- `max_passes`
- `batch_concurrency`
- `enable_fuzzy_alignment`
- `fuzzy_alignment_threshold`
- `accept_partial_exact`
- `stop_when_no_new_extractions`
- `allow_unresolved`

## Behavior That Affects Output

- If `allow_unresolved=False` (default), unresolved candidates are counted in metrics but not returned in `documents[*].extractions`.
- If `strict_example_alignment=True` (default in `ExtractionTask`) and examples are unresolved, extraction raises `ExampleValidationError` before runtime execution.
- If reconciliation workforce fails at runtime, the engine falls back to deterministic canonical-claim construction and records warnings.

## Practical Baseline

```python
from sourcery.contracts import ExtractOptions, RuntimeConfig

runtime = RuntimeConfig(
    model="deepseek/deepseek-chat",
    temperature=0.0,
)

options = ExtractOptions(
    max_chunk_chars=1200,
    context_window_chars=200,
    max_passes=2,
    batch_concurrency=16,
    stop_when_no_new_extractions=True,
    allow_unresolved=False,
)
```

## Throughput-Oriented Profile

```python
options = ExtractOptions(
    max_chunk_chars=1800,
    context_window_chars=120,
    max_passes=1,
    batch_concurrency=32,
    stop_when_no_new_extractions=True,
)
```

## Quality-Oriented Profile

```python
options = ExtractOptions(
    max_chunk_chars=900,
    context_window_chars=280,
    max_passes=3,
    enable_fuzzy_alignment=True,
    fuzzy_alignment_threshold=0.82,
    allow_unresolved=False,
)
```

## Tuning Sequence

1. Freeze schema and examples first.
2. Set `temperature=0.0`.
3. Measure baseline metrics and warnings.
4. Increase `max_passes` only when extraction recall improves materially.
5. Increase concurrency only if provider limits and system resources allow it.
