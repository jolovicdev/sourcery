# Runtime Internals

## Engine

`SourceryEngine` (`sourcery/runtime/engine.py`) orchestrates the extraction lifecycle:

- runtime construction,
- pass scheduling,
- chunk runtime execution,
- alignment and merge,
- optional reconciliation,
- metrics and trace finalization.

Public entry points:

- `SourceryEngine.extract(request)`
- `SourceryEngine.aextract(request)`
- `SourceryEngine.replay_run(request, raw_run_id)`

## Runtime Boundary

Protocols in `sourcery/runtime/base.py` define black-box contracts:

- `ChunkRuntime`
- `DocumentReconciliationRuntime`

Any runtime implementation that satisfies these interfaces can be swapped in.

## BlackGeorge Runtime Composition

`BlackGeorgeRuntime` combines focused mixins:

- `blackgeorge_retry_mixin.py`: retry/backoff and paused-run resume.
- `blackgeorge_refinement_mixin.py`: per-document session refinement contexts.
- `blackgeorge_flow_mixin.py`: chunk flow execution and report normalization.
- `blackgeorge_reconciliation_mixin.py`: document-level reconciliation workforce.

`model_gateway.py` builds per-entity response schema variants and parses structured candidate output.

## Observability and Replay

- Runtime subscribes to desk event bus (`run.*`, `worker.*`, `step.*`, `llm.*`, `tool.*`).
- Events are normalized to `EventRecord` and attached to `ExtractionRunTrace`.
- `replay_run` reads raw run data/events from run store for audits and debugging.

## Reconciliation Fallback Behavior

When reconciliation is enabled:

1. Deterministic fallback canonical claims are prepared first.
2. Workforce reconciliation is attempted if `use_workforce=True`.
3. If workforce fails with `SourceryRuntimeError`, engine returns fallback claims and warning text.
4. Non-Sourcery unexpected exceptions are propagated.
