# System Overview

Sourcery is structured as replaceable black boxes around typed contracts.

## Primary Primitives

Defined in `sourcery/contracts/models.py`:

- `SourceDocument`
- `TextChunk`
- `ExtractionCandidate`
- `AlignedExtraction`
- `DocumentResult`
- `CanonicalClaim`
- `ExtractRequest`
- `ExtractResult`

These primitives are the stable interface. Internal implementation can change without breaking user code if these contracts remain consistent.

## Module Boundaries

- `sourcery/contracts`: request/result/runtime contracts.
- `sourcery/pipeline`: deterministic chunking, prompt compilation, alignment, merge.
- `sourcery/runtime`: model invocation orchestration and retries.
- `sourcery/ingest`: source normalization into `SourceDocument`.
- `sourcery/io`: JSONL persistence and HTML review surfaces.
- `sourcery/observability`: run trace and event collection.
- `sourcery/benchmarks`: benchmark CLI and comparative tooling.

## Execution Flow

1. Validate `ExtractRequest` and task examples.
2. Normalize input documents.
3. Plan chunks per extraction pass.
4. Execute runtime batch for chunks.
5. Align candidates to source spans.
6. Merge non-overlapping resolved extractions.
7. Optionally reconcile canonical claims.
8. Emit `ExtractResult` with metrics, warnings, and run trace.

## Determinism Notes

Determinism is strongest in pipeline logic (`chunking`, `aligner`, `merger`).
Runtime behavior may vary with provider/model behavior, but deterministic options plus strict examples reduce drift.
