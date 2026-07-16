# Sourcery Runtime Internals: Async, Streaming, and Replay

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
- `SourceryEngine.extract_stream(request)`
- `SourceryEngine.replay_run(request, raw_run_id)`

`extract_stream(...)` is Sourcery-level result streaming: chunks still run through the normal runtime path, but the engine emits `StreamExtractionAdded`, `StreamChunkDone`, and `StreamPassDone` events as merged results become available.

## Runtime Boundary

Protocols in `sourcery/runtime/base.py` define black-box contracts:

- `ChunkRuntime`
- `DocumentReconciliationRuntime`
- `AsyncDocumentReconciliationRuntime`

Any runtime implementation that satisfies these interfaces can be swapped in.

`EngineDependencies` wires the runtime factory, prompt compiler, example validator, chunk planner, aligner, merger, and trace collector. This keeps the engine testable without making those dependency hooks decorative.

## BlackGeorge Runtime

`BlackGeorgeRuntime` is one concrete adapter around BlackGeorge 1.3.0. It owns retry and paused-run policy, per-document session refinement, chunk flow normalization, and optional document reconciliation. Runtime protocols stay at the engine boundary rather than being repeated as mixin self-types.

`model_gateway.py` builds per-entity response schema variants and parses structured candidate output.

## Observability and Replay

- Runtime subscribes to every desk event and reads completed run events from the run store.
- Events are normalized to `EventRecord` and attached to `ExtractionRunTrace`.
- `replay_run` reads raw run data/events from run store for audits and debugging.

## Reconciliation Fallback Behavior

When reconciliation is enabled:

1. Deterministic fallback canonical claims are prepared first.
2. Workforce reconciliation is attempted if `use_workforce=True`.
3. If workforce fails with `SourceryRuntimeError`, engine returns fallback claims and warning text.
4. Non-Sourcery unexpected exceptions are propagated.
