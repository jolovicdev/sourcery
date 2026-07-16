# SourceryForge: Source-Grounded LLM Document Extraction for Python

**SourceryForge** is an open-source Python framework for extracting structured data from
unstructured text, PDFs, HTML pages, URLs, and OCR-processed images with large language models.
The PyPI distribution is `sourceryforge`; the Python import is `sourcery`.

Define extraction schemas with Pydantic and receive typed entities with exact source spans.
Sourcery handles deterministic chunking, multi-pass extraction, cross-chunk refinement, mention
reconciliation, JSONL export, HTML review, and stored-run replay.

## Why use Sourcery for LLM document extraction?

- **Typed structured output:** Define entity attributes with Pydantic models.
- **Source-grounded results:** Every resolved extraction includes exact character offsets.
- **Long-document processing:** Split large sources into deterministic chunks with context.
- **Entity reconciliation:** Combine repeated mentions into canonical claims.
- **Reviewable output:** Export JSONL or generate interactive HTML review pages.
- **Runtime diagnostics:** Inspect typed errors, event traces, retry attempts, and stored runs.
- **Async and streaming APIs:** Run native async extraction or consume chunk-level progress events.

## Install SourceryForge

Sourcery requires Python 3.12 or newer.

```bash
uv add sourceryforge
```

Install PDF ingestion support:

```bash
uv add "sourceryforge[ingest]"
```

Set the credential required by your selected model provider. For DeepSeek:

```bash
export DEEPSEEK_API_KEY="..."
```

Set `RuntimeConfig.model` to a provider/model route supported by your BlackGeorge runtime setup.

## Extract structured data with Python

```python
from pydantic import BaseModel

import sourcery
from sourcery import (
    EntitySchemaSet,
    EntitySpec,
    ExtractRequest,
    ExtractionExample,
    ExtractionTask,
    ExampleExtraction,
    RuntimeConfig,
)


class PersonAttributes(BaseModel):
    role: str | None = None


text = "Alice Johnson is the CEO of Acme Robotics."

request = ExtractRequest(
    documents=text,
    task=ExtractionTask(
        instructions="Extract every named person and their role.",
        schema=EntitySchemaSet(
            entities=[
                EntitySpec(
                    name="person",
                    attributes_model=PersonAttributes,
                )
            ]
        ),
        examples=[
            ExtractionExample(
                text="Bob Chen is the CTO.",
                extractions=[
                    ExampleExtraction(
                        entity="person",
                        text="Bob Chen",
                        attributes={"role": "CTO"},
                    )
                ],
            )
        ],
    ),
    runtime=RuntimeConfig(
        model="deepseek/deepseek-v4-flash",
        temperature=0.0,
    ),
)

result = sourcery.extract(request)
extraction = result.documents[0].extractions[0]

assert isinstance(extraction.attributes, PersonAttributes)
assert text[extraction.char_start : extraction.char_end] == extraction.text

print(extraction.text)
print(extraction.attributes.role)
print(extraction.char_start, extraction.char_end)
```

## How Sourcery extracts information from documents

1. Validate the extraction task, Pydantic entity schemas, and few-shot examples.
2. Split each document into deterministic text chunks with source offsets and optional context.
3. Ask the configured LLM for structured candidates that match the entity schemas.
4. Align every candidate to an exact, fuzzy, partial, or unresolved source span.
5. Merge overlapping results across chunks and extraction passes.
6. Optionally reconcile repeated mentions into canonical claims.
7. Return typed documents, metrics, warnings, provenance, and runtime events.

Sourcery owns the deterministic extraction pipeline. Model output is never presented as grounded
unless it can be aligned back to the source text.

## Extract from PDFs, HTML, URLs, and images

The source loaders accept:

- inline text,
- plain-text and HTML files,
- PDF documents through `pypdf`,
- web URLs,
- raw HTML,
- image files through a configurable vision-language OCR backend.

Use `sourcery.extract_from_sources(...)` when you want loading and extraction in one call. PDF
loading is text-extraction first. Scanned documents can use the VLM OCR interface before entering
the normal typed extraction pipeline.

## Source-grounded Pydantic output

Each aligned extraction can include:

- the entity type and extracted text,
- typed Pydantic attributes,
- character and token offsets,
- alignment status and confidence,
- model, worker, chunk, pass, and run provenance.

Each document can also contain canonical claims produced by document-level reconciliation. The
full result includes run metrics, warnings, chunk identifiers, and normalized runtime events.

Persist or inspect results with:

- `save_extract_result_jsonl(...)` for machine-readable JSONL,
- `write_document_html(...)` for source-span visualization,
- `write_reviewer_html(...)` for approve, reject, search, filter, JSONL, and CSV workflows.

## Long documents, async extraction, and streaming

Sourcery supports deterministic multi-pass extraction, configurable chunk sizes, previous-chunk
context, and bounded batch concurrency.

- `sourcery.extract(...)` runs the synchronous API.
- `sourcery.aextract(...)` runs native async extraction.
- `SourceryEngine.extract_stream(...)` yields extraction, chunk, and pass events.
- `SourceryEngine.replay_run(...)` reads stored BlackGeorge run data and events.

Chunks run in bounded concurrent batches. Events are emitted in deterministic chunk order after
each batch finishes. This is progress streaming, not token streaming.

## Compare Sourcery with LangExtract

The included benchmark compares Sourcery and LangExtract on Gutenberg text samples. It records
elapsed time, grounded extractions, unresolved extractions, and unique grounded entities for each
framework.

Install the benchmark dependencies from the repository root:

```bash
uv sync --extra benchmark
```

Run the multilingual benchmark:

```bash
uv run sourcery-benchmark \
  --text-types english,japanese,french,spanish \
  --max-chars 4500 \
  --max-passes 2 \
  --sourcery-model deepseek/deepseek-v4-flash
```

The compatibility wrapper runs the same CLI entry point:

```bash
uv run benchmark_compare.py --text-types english
```

Reports are written to `benchmark_results/`. The benchmark follows a similar Gutenberg sampling
flow to LangExtract's benchmark, but it is not a byte-for-byte port.

## Runtime architecture: Sourcery and BlackGeorge

Sourcery is an application layer on top of
[BlackGeorge](https://github.com/jolovicdev/blackgeorge) runtime primitives such as `Desk`, `Flow`,
`Worker`, `Workforce`, `RunStore`, and `EventBus`.

- Sourcery handles schemas, prompts, chunking, alignment, merging, reconciliation, and outputs.
- BlackGeorge handles model execution, orchestration, events, pause and resume, and run storage.

BlackGeorge is a required runtime dependency. Sourcery does not maintain a separate provider router
or orchestration engine.

## LLM document extraction use cases

- Regulatory compliance reports and policy updates.
- SEC filings, annual reports, and earnings-call transcripts.
- Contract clauses, obligations, dates, and renewal terms.
- Clinical trial protocols, treatment arms, endpoints, and adverse events.
- Cyber threat reports, indicators, malware families, and CVEs.
- Industrial maintenance logs, fault codes, parts, and repair actions.
- Public meeting minutes, motions, votes, and action items.
- Freight documents, cargo descriptions, ports, and container identifiers.
- Property inspection reports, defects, severity, and recommended repairs.
- Grant and RFP eligibility rules, deadlines, deliverables, and scoring criteria.

## Documentation and examples

- [Installation and provider setup](docs/getting-started/installation.md)
- [Five-minute extraction quickstart](docs/getting-started/quickstart.md)
- [Complete usage guide](USAGE.md)
- [Runnable Python examples](CODE_EXAMPLES.md)
- [Public API reference](docs/reference/public-api.md)
- [Runtime configuration and tuning](docs/guides/runtime-and-tuning.md)
- [Outputs and reviewer guide](docs/guides/outputs-and-reviewer.md)
- [Quickstart notebook](examples/notebooks/sourcery_quickstart.ipynb)
- [PDF workflow notebook](examples/notebooks/sourcery_pdf_workflow.ipynb)
- [Published documentation site](https://jolovicdev.github.io/sourcery/)

## Project layout

- `sourcery/contracts`: public request, runtime, and result contracts.
- `sourcery/pipeline`: prompt compilation, chunking, alignment, and merging.
- `sourcery/runtime`: extraction engine and BlackGeorge integration.
- `sourcery/ingest`: text, file, PDF, HTML, URL, and VLM OCR loaders.
- `sourcery/io`: JSONL persistence, visualization, and reviewer UI.
- `sourcery/observability`: normalized run trace collection.
- `sourcery/benchmarks`: Sourcery and LangExtract benchmark runner.

## Development and validation

Install the common development extras:

```bash
uv sync --extra dev --extra ingest --extra docs --extra benchmark
```

Run the release checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run --extra dev pytest -q
uv run --extra docs mkdocs build --strict
```

## Capabilities and limits

### PDF and scanned-document extraction

The ingestion extra uses `pypdf` for text-based PDFs. Scanned pages require a vision-language OCR
backend before they enter the normal extraction pipeline.

### Typed Pydantic results

Each `EntitySpec` references a Pydantic attribute model. Validated attributes retain their concrete
model fields in direct and nested result serialization.

### Source grounding

Every candidate is checked against its source chunk. Returned extractions carry one of four
alignment statuses: `exact`, `fuzzy`, `partial`, or `unresolved`. Resolved extractions also receive
source character offsets.

### Model providers

Set `RuntimeConfig.model` to a provider/model route supported by BlackGeorge and provide the matching
credential through environment variables. Sourcery passes model execution to the BlackGeorge
runtime.

### Async and streaming extraction

Use `sourcery.aextract(...)` for native async extraction and `SourceryEngine.extract_stream(...)`
for chunk-level progress events. Streaming reports chunk progress, not model tokens.

## License

SourceryForge is licensed under the MIT License. See [LICENSE](LICENSE).
