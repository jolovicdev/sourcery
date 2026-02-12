# Public API

Top-level exports are defined in `sourcery/__init__.py`.

## Core Functions

```python
extract(request, engine=None) -> ExtractResult
aextract(request, engine=None) -> ExtractResult
extract_from_sources(sources, *, task, runtime, options=None, engine=None) -> ExtractResult
aextract_from_sources(sources, *, task, runtime, options=None, engine=None) -> ExtractResult
```

## Runtime Entry Points

```python
SourceryEngine.extract(request) -> ExtractResult
SourceryEngine.aextract(request) -> ExtractResult
SourceryEngine.replay_run(request, raw_run_id) -> tuple[dict[str, object] | None, list[EventRecord]]
```

## Top-Level Contract Exports (`import sourcery`)

- `EntitySpec`, `EntitySchemaSet`
- `ExtractionTask`, `ExtractionExample`, `ExampleExtraction`
- `ExtractRequest`, `ExtractOptions`, `ExtractResult`
- `RuntimeConfig`, `RetryPolicy`, `SessionRefinementConfig`, `ReconciliationConfig`
- `AlignedExtraction`, `CanonicalClaim`, `DocumentResult`, `DocumentReconciliationReport`
- `ExtractionRunTrace`, `RunMetrics`, `SourceDocument`

## Ingestion Exports

From `sourcery.ingest`:

- `load_source_document(...)`
- `load_source_documents(...)`
- `load_pdf_document(...)`
- `load_html_document(...)`
- `load_url_document(...)`
- `load_ocr_image_document(...)`

Top-level shortcut (`import sourcery`) includes only:

- `load_source_document(...)`
- `load_source_documents(...)`

## IO Exports

From `sourcery.io`:

- `save_extract_result_jsonl(...)`
- `iter_document_rows(...)`
- `load_document_results_jsonl(...)`
- `render_document_html(...)`
- `write_document_html(...)`
- `render_reviewer_html(...)`
- `write_reviewer_html(...)`
- `visualize(...)`

Top-level shortcut (`import sourcery`) includes:

- `write_reviewer_html(...)`

## Convenience Example

```python
import sourcery
from sourcery.contracts import ExtractionTask, RuntimeConfig

result = sourcery.extract_from_sources(
    ["sample.pdf", "https://example.com/article"],
    task=ExtractionTask(...),
    runtime=RuntimeConfig(model="deepseek/deepseek-chat"),
)
```
