# Installation

## Requirements

- Python `>=3.12`
- `uv` package manager
- API key for your model provider (for example `DEEPSEEK_API_KEY`)

Base runtime dependency is `blackgeorge` (installed automatically with `sourceryforge`).

PyPI distribution name is `sourceryforge`, while Python import path remains `sourcery`.

## Install Dependencies

Core package only:

```bash
uv sync
```

Install from PyPI:

```bash
pip install sourceryforge
```

With ingestion adapters (PDF/OCR/URL workflows):

```bash
uv sync --extra ingest
```

With dev tooling (tests, lint, type-check):

```bash
uv sync --extra dev --extra ingest
```

With docs tooling:

```bash
uv sync --extra docs
```

## Provider Credentials

Sourcery runtime calls are delegated to the configured runtime/provider (`RuntimeConfig.model`).
This repository itself explicitly reads these keys in helper scripts:

```bash
export DEEPSEEK_API_KEY="..."
```

```bash
export OPENROUTER_API_KEY="..."
```

Set the credentials required by your selected model route before calling extraction.
For example, `RuntimeConfig(model="deepseek/deepseek-chat")` typically requires `DEEPSEEK_API_KEY`.

Benchmark scripts use `DEEPSEEK_API_KEY` or `OPENROUTER_API_KEY` depending on `--sourcery-model`.

## Smoke Test

```bash
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

## Validate Full Dev Environment

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check sourcery tests
uv run --extra dev mypy sourcery
```
