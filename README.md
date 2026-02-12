# Sourcery: Schema-First Document Extraction (LangExtract Alternative on BlackGeorge)

Sourcery is a **schema-first LLM extraction framework** for turning unstructured documents into typed, grounded entities and claims.

It is built on [**BlackGeorge**](https://github.com/jolovicdev/blackgeorge) runtime primitives (`Desk`, `Flow`, `Worker`, `Workforce`, `RunStore`, `EventBus`) and is designed as a clean-break alternative to LangExtract.

## What Is Sourcery

Sourcery is for people building:

- document AI pipelines,
- compliance and legal extraction systems,
- financial filing intelligence,
- contract and policy analyzers,
- review workflows with human approval.

Core idea:

1. Define extraction contracts in **Pydantic v2**.
2. Run deterministic chunked extraction with LLM structured output.
3. Align results to source offsets.
4. Reconcile at document-level into canonical claims.
5. Review/export via JSONL + HTML reviewer.

## Why Sourcery vs LangExtract

Sourcery is optimized for **type safety + runtime reliability + deterministic post-processing**.

- Pydantic contracts are first-class (`EntitySpec.attributes_model`).
- BlackGeorge-native runtime orchestration (no custom provider router stack).
- Deterministic alignment statuses (`exact`, `fuzzy`, `partial`, `unresolved`).
- Deterministic merge behavior across passes.
- Typed error taxonomy for provider/runtime/pipeline/ingestion failures.
- Run replay seam via BlackGeorge run store.
- Built-in reviewer UI (search/filter/approve/export).
- Document-level reconciliation support (Workforce + Blackboard + resolver worker).

## BlackGeorge Relationship

Sourcery is an application layer **on top of** [**BlackGeorge**](https://github.com/jolovicdev/blackgeorge).

- Sourcery handles extraction domain logic.
- BlackGeorge handles model execution, workflow orchestration, events, pause/resume, and run storage.

This means BlackGeorge is a hard runtime dependency in this project.

## Features

- Schema-first extraction with Pydantic models.
- Ingestion adapters: text, file, PDF, HTML, URL, OCR image.
- Deterministic chunking and alignment.
- Multi-pass extraction with stop-when-no-new-results.
- Cross-chunk refinement and document-level reconciliation.
- Session-based refinement mode.
- Reviewer HTML UI + export to JSONL/CSV.
- Run tracing and replay.

## Install

```bash
uv sync --extra dev --extra ingest
```

PyPI distribution name: `sourceryforge`  
Python import path: `sourcery`

```bash
pip install sourceryforge (uv add sourceryforge)
```

If you want Sourcery vs LangExtract benchmark tooling:

```bash
uv sync --extra benchmark
```

Set your provider key (example):

```bash
export DEEPSEEK_API_KEY="..."
```

Set `RuntimeConfig.model` to a provider/model route supported by your BlackGeorge runtime setup.

## Reproducible Benchmark

Run the benchmark from this repo root:

```bash
uv run sourcery-benchmark --text-types english,japanese,french,spanish --max-chars 4500 --max-passes 2 --sourcery-model deepseek/deepseek-chat
```

Run it from any directory:

```bash
uv run --project /path/to/sourcery sourcery-benchmark --text-types english
```
Or run the compatibility wrapper:

```bash
uv run benchmark_compare.py --text-types english
```

Output JSON is written to `benchmark_results/` and includes:

- run settings,
- tokenization throughput table,
- per-language Sourcery and LangExtract extraction metrics,
- aggregate summary for both frameworks.

### Benchmark Port Scope

This is based on LangExtract `benchmarks/benchmark.py` behavior, but it is not a byte-for-byte clone.

- Ported: Gutenberg text sampling flow, per-language extraction runs, retry behavior, timing, grounded/unresolved metrics, JSON output artifacts.

## Quickstart

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
        instructions="Extract people.",
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
```

More examples: `CODE_EXAMPLES.md`
Full usage and API guide: `USAGE.md`
Notebook workflows: `examples/notebooks/sourcery_quickstart.ipynb`, `examples/notebooks/sourcery_pdf_workflow.ipynb`

## Project Structure

- `sourcery/contracts`: public types and contracts.
- `sourcery/pipeline`: chunking, prompt compiler, aligner, merger.
- `sourcery/runtime`: engine + BlackGeorge runtime integration.
- `sourcery/ingest`: document loaders and adapters.
- `sourcery/io`: JSONL, visualization, reviewer UI.
- `sourcery/observability`: run trace collection.

## Validation

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check sourcery tests
uv run --extra dev mypy sourcery
```

## Documentation Site

Build and serve project docs with MkDocs:

```bash
uv run --extra docs mkdocs serve
uv run --extra docs mkdocs build --strict
```

## Common Use Cases

- Regulatory compliance extraction.
- SEC filing and earnings-call intelligence.
- Contract clause extraction and renewal tracking.
- Policy change monitoring.
- Research paper benchmark extraction.
- Incident/postmortem structure mining.

## License

Licensed under the MIT License. See `LICENSE`.
