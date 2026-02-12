# File-by-File Map

This map links each tracked module to its responsibility.

## Root Package

- `sourcery/__init__.py`: public export surface.
- `sourcery/api.py`: top-level extraction convenience functions.
- `sourcery/exceptions.py`: typed exception taxonomy.

## Contracts

- `sourcery/contracts/models.py`: all request/runtime/result primitives.
- `sourcery/contracts/__init__.py`: contracts re-export surface.

## Pipeline

- `sourcery/pipeline/chunking.py`: chunk planning and offsets.
- `sourcery/pipeline/prompt_compiler.py`: prompt envelope generation.
- `sourcery/pipeline/aligner.py`: candidate-to-text grounding.
- `sourcery/pipeline/merger.py`: overlap resolution.
- `sourcery/pipeline/example_validator.py`: few-shot validation.
- `sourcery/pipeline/__init__.py`: pipeline re-exports.

## Runtime

- `sourcery/runtime/base.py`: runtime protocol contracts.
- `sourcery/runtime/interfaces.py`: protocol re-export.
- `sourcery/runtime/engine.py`: extraction orchestration.
- `sourcery/runtime/errors.py`: provider error classification.
- `sourcery/runtime/model_gateway.py`: schema + parser bridge.
- `sourcery/runtime/blackgeorge_models.py`: runtime payload adapters.
- `sourcery/runtime/blackgeorge_protocols.py`: internal runtime typing.
- `sourcery/runtime/blackgeorge_retry_mixin.py`: retry/backoff/pause logic.
- `sourcery/runtime/blackgeorge_refinement_mixin.py`: refinement context handling.
- `sourcery/runtime/blackgeorge_flow_mixin.py`: chunk extraction flow.
- `sourcery/runtime/blackgeorge_reconciliation_mixin.py`: canonical-claim workflow.
- `sourcery/runtime/blackgeorge_runtime.py`: composed runtime implementation.
- `sourcery/runtime/__init__.py`: runtime public exports.

## Ingestion

- `sourcery/ingest/loaders.py`: all source loaders.
- `sourcery/ingest/__init__.py`: ingestion public exports.

## IO

- `sourcery/io/jsonl.py`: JSONL persistence helpers.
- `sourcery/io/visualization.py`: read-only visual viewer rendering.
- `sourcery/io/reviewer.py`: interactive reviewer rendering and export.
- `sourcery/io/__init__.py`: IO export surface.

## Observability

- `sourcery/observability/trace.py`: run event collection and trace finalization.
- `sourcery/observability/__init__.py`: observability exports.

## Benchmarks

- `sourcery/benchmarks/config.py`: benchmark config constants.
- `sourcery/benchmarks/gutenberg.py`: text sampling helpers.
- `sourcery/benchmarks/run.py`: benchmark CLI implementation.
- `sourcery/benchmarks/__init__.py`: benchmark exports.

## Test and Utility Scripts

- `benchmark_compare.py`: thin CLI entry wrapper for benchmark run.

## Tests

- `tests/conftest.py`: shared fixtures and fake runtimes.
- `tests/test_contracts.py`: contract validation.
- `tests/test_chunking.py`: chunk planning behavior.
- `tests/test_aligner.py`: alignment behavior.
- `tests/test_merger.py`: merge precedence behavior.
- `tests/test_example_validator.py`: example alignment validation.
- `tests/test_engine.py`: engine orchestration behavior.
- `tests/test_api.py`: public API function behavior.
- `tests/test_ingest.py`: ingestion loader behavior.
- `tests/test_io.py`: JSONL/viewer/reviewer behavior.
- `tests/test_runtime_errors.py`: runtime error classifier behavior.
- `tests/test_model_gateway.py`: response parsing behavior.
- `tests/test_blackgeorge_runtime.py`: runtime mixin regressions.
- `tests/test_benchmarks.py`: benchmark utility behavior.
