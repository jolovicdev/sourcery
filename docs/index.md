# Sourcery

Sourcery is a schema-first extraction framework for turning unstructured text, files, URLs, and documents into typed, grounded entities.

If you can define your target entities as Pydantic models, you can run reproducible extraction pipelines with traceability, retry policy, and reviewable outputs.

## What You Build With It

- Typed entity extraction with strict schema validation.
- Character-grounded spans (`char_start`, `char_end`) for each extraction.
- Deterministic chunking, alignment, and merge behavior.
- JSONL + HTML outputs for downstream systems and human review.

## Core Boundaries

1. Contracts: `sourcery/contracts` defines all request/result primitives.
2. Pipeline: `sourcery/pipeline` handles chunking, prompt envelopes, alignment, merge.
3. Runtime: `sourcery/runtime` executes model calls and orchestration.
4. IO + Review: `sourcery/io` persists and visualizes extraction results.

## Start Here

1. Install and configure credentials: [Getting Started / Installation](getting-started/installation.md)
2. Run first extraction in <5 minutes: [Getting Started / Quickstart](getting-started/quickstart.md)
3. Build from mixed sources (PDF/URL/text): [Guides / Build A Pipeline](guides/build-a-pipeline.md)
4. Tune reliability and throughput: [Guides / Runtime And Tuning](guides/runtime-and-tuning.md)

## Minimal End-to-End Path

```bash
uv sync --extra ingest
export DEEPSEEK_API_KEY="..."
uv run python - <<'PY'
from pydantic import BaseModel
import sourcery
from sourcery.contracts import EntitySchemaSet, EntitySpec, ExtractRequest, ExtractionExample, ExtractionTask, ExampleExtraction, RuntimeConfig

class PersonAttrs(BaseModel):
    role: str | None = None

request = ExtractRequest(
    documents="Alice is CTO at Acme.",
    task=ExtractionTask(
        instructions="Extract people and role if present.",
        schema=EntitySchemaSet(entities=[EntitySpec(name="person", attributes_model=PersonAttrs)]),
        examples=[
            ExtractionExample(
                text="Bob is CEO.",
                extractions=[ExampleExtraction(entity="person", text="Bob", attributes={"role": "CEO"})],
            )
        ],
    ),
    runtime=RuntimeConfig(model="deepseek/deepseek-chat"),
)

result = sourcery.extract(request)
print(result.metrics.model_dump(mode="json"))
PY
```

If you do not use DeepSeek, set the provider key required by your selected model route.

## Documentation Build

Serve locally:

```bash
uv run --extra docs mkdocs serve
```

Build static docs with strict validation:

```bash
uv run --extra docs mkdocs build --strict
```
