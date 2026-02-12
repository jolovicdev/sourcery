# Sourcery Usage Guide

## What Sourcery Is

Sourcery is both:

1. A **Python library** you import (`import sourcery`) to run schema-first extraction.
2. A **reference project** with ingestion adapters, HTML reviewer UI, and runnable integration scripts.

Use it as a library inside your app, and use this repository as a production template.

## When To Use Sourcery

Use Sourcery when you need:

- typed extraction contracts (Pydantic models),
- grounded spans (`char_start`, `char_end`) for every extraction,
- deterministic chunking/alignment/merge behavior,
- optional document-level reconciliation into canonical claims,
- human review/export workflows.

## Install

Python requirement: `>=3.12`

Minimal runtime:

```bash
uv sync
```

With ingestion adapters (PDF/OCR/URL HTML):

```bash
uv sync --extra ingest
```

With dev tooling:

```bash
uv sync --extra dev --extra ingest
```

Set provider credentials for the model route you use in `RuntimeConfig.model` (for example `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.).

## Core Public API

Import-level API (`sourcery/__init__.py`):

1. `extract(request: ExtractRequest, engine: SourceryEngine | None = None) -> ExtractResult`
2. `aextract(request: ExtractRequest, engine: SourceryEngine | None = None) -> ExtractResult`
3. `extract_from_sources(sources, *, task, runtime, options=None, engine=None) -> ExtractResult`
4. `aextract_from_sources(...) -> ExtractResult`
5. `SourceryEngine` with `.extract(...)`, `.aextract(...)`, `.replay_run(...)`

## Data Contracts You Define

### 1) `EntitySpec`

- `name: str`
- `attributes_model: type[BaseModel]`

### 2) `EntitySchemaSet`

- `entities: list[EntitySpec]`

### 3) `ExtractionTask`

- `instructions: str`
- `schema: EntitySchemaSet`
- `examples: list[ExtractionExample]`
- `strict_example_alignment: bool = True`

### 4) `ExtractRequest`

- `documents: list[SourceDocument] | str`
- `task: ExtractionTask`
- `options: ExtractOptions = ExtractOptions()`
- `runtime: RuntimeConfig`

### 5) `ExtractResult`

- `documents: list[DocumentResult]`
- `run_trace: ExtractionRunTrace`
- `metrics: RunMetrics`
- `warnings: list[str]`

`DocumentResult` includes:

- `extractions: list[AlignedExtraction]`
- `canonical_claims: list[CanonicalClaim]`

## Runtime Config (`RuntimeConfig`)

Required:

- `model: str`

Core options:

- `temperature: float = 0.0`
- `max_tokens: int | None = None`
- `stream: bool = False`
- `storage_dir: str = ".sourcery"`
- `respect_context_window: bool = True`

Reliability:

- `retry: RetryPolicy`
  - `max_attempts=3`
  - `initial_backoff_seconds=0.75`
  - `max_backoff_seconds=8.0`
  - `backoff_multiplier=2.0`
  - `retry_on_rate_limit=True`
  - `retry_on_transient_errors=True`
  - `auto_resume_paused_runs=True`
  - `max_pause_resumes=5`

Session refinement (optional):

- `session_refinement: SessionRefinementConfig`
  - `enabled=False`
  - `max_turns=1`
  - `context_chars=320`

Document-level reconciliation (optional):

- `reconciliation: ReconciliationConfig`
  - `enabled=False`
  - `use_workforce=True`
  - `min_mentions_for_claim=1`
  - `max_claims=200`

## Extraction Options (`ExtractOptions`)

- `max_chunk_chars=1200`
- `context_window_chars=200`
- `max_passes=2`
- `batch_concurrency=16`
- `enable_fuzzy_alignment=True`
- `fuzzy_alignment_threshold=0.82`
- `accept_partial_exact=False`
- `stop_when_no_new_extractions=True`
- `allow_unresolved=False`

## Minimal Example (Inline Text)

```python
from pydantic import BaseModel
import sourcery
from sourcery.contracts import (
    EntitySchemaSet,
    EntitySpec,
    ExtractRequest,
    ExtractionExample,
    ExtractionTask,
    ExampleExtraction,
    RuntimeConfig,
)

class PersonAttrs(BaseModel):
    role: str | None = None

request = ExtractRequest(
    documents="Alice is the CEO of Acme.",
    task=ExtractionTask(
        instructions="Extract person entities.",
        schema=EntitySchemaSet(
            entities=[EntitySpec(name="person", attributes_model=PersonAttrs)]
        ),
        examples=[
            ExtractionExample(
                text="Bob is the CTO.",
                extractions=[
                    ExampleExtraction(entity="person", text="Bob", attributes={"role": "CTO"})
                ],
            )
        ],
    ),
    runtime=RuntimeConfig(model="deepseek/deepseek-chat"),
)

result = sourcery.extract(request)
print(result.metrics.model_dump(mode="json"))
for ext in result.documents[0].extractions:
    print(ext.entity, ext.text, ext.char_start, ext.char_end, ext.alignment_status)
```

Notebook equivalent: `examples/notebooks/sourcery_quickstart.ipynb`

## Extract From Files / PDFs / URLs / Images

Use the source-based helper:

```python
result = sourcery.extract_from_sources(
    ["1706.03762v7.pdf", "https://example.com/article.html"],
    task=task,
    runtime=RuntimeConfig(model="deepseek/deepseek-chat"),
)
```

Supported ingestion via `load_source_document(s)`:

1. Inline text
2. Text files
3. PDF files (`pypdf`)
4. HTML files / raw HTML
5. URLs
6. OCR image files (`Pillow` + `pytesseract`)

Notes:

- PDF loader is text-extraction first (`pypdf`).
- OCR is currently image-based ingestion, not multimodal LLM extraction.

Notebook equivalent: `examples/notebooks/sourcery_pdf_workflow.ipynb`

## Async Usage

```python
result = await sourcery.aextract(request)
```

## Advanced Engine Usage

```python
from sourcery.runtime import SourceryEngine

engine = SourceryEngine()
result = engine.extract(request)

raw_run_id = result.documents[0].extractions[0].provenance.raw_run_id
if raw_run_id:
    replay, events = engine.replay_run(request, raw_run_id)
    print(replay["status"] if replay else None, len(events))
```

## Enabling Reconciliation + Session Refinement

```python
runtime = RuntimeConfig(
    model="deepseek/deepseek-chat",
    session_refinement={"enabled": True, "max_turns": 1, "context_chars": 320},
    reconciliation={"enabled": True, "use_workforce": True, "max_claims": 100},
)
```

What this does:

1. Session refinement adds multi-turn continuity hints per chunk.
2. Reconciliation runs document-level resolver workflow and returns `canonical_claims`.

## Outputs and Review

### Save JSONL

```python
from sourcery.io import save_extract_result_jsonl
save_extract_result_jsonl(result, "output/result.jsonl")
```

### Generate HTML viewer

```python
from sourcery.io import write_document_html
write_document_html(result.documents[0], "output/document.viewer.html")
```

### Generate reviewer UI

```python
from sourcery.io import write_reviewer_html
write_reviewer_html(result.documents[0], "output/document.reviewer.html")
```

Reviewer supports:

- search,
- entity/status filters,
- approve/reject/reset,
- export approved JSONL/CSV.

## Scripted End-to-End Runs

### Benchmark comparison wrapper

```bash
uv run benchmark_compare.py --text-types english
```

## Error Model

Important exception classes (`sourcery/exceptions.py`):

- `SourceryError`
- `SourceryRuntimeError`
- `SourceryProviderError`
- `SourceryRateLimitError`
- `SourceryRetryExhaustedError`
- `SourceryPausedRunError`
- `SourceryPipelineError`
- `SourceryIngestionError`
- `SourceryDependencyError`

## Validation Commands

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check sourcery tests
uv run --extra dev mypy sourcery
```

## Production Notes

1. Treat schemas as API contracts and version them.
2. Start with strict examples and deterministic options.
3. Enable reconciliation for long documents where alias/coreference matters.
4. Keep reviewer approval in-the-loop for high-stakes workflows.
5. Persist JSONL + run trace for audit and replay.
