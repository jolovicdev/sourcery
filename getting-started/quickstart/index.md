# Quickstart

This quickstart creates a typed extraction task, runs extraction, and writes reviewable outputs.

## 1. Create `quickstart.py`

```
from pathlib import Path

from pydantic import BaseModel

import sourcery
from sourcery.contracts import (
    EntitySchemaSet,
    EntitySpec,
    ExtractRequest,
    ExtractOptions,
    ExtractionExample,
    ExtractionTask,
    ExampleExtraction,
    RuntimeConfig,
)
from sourcery.io import save_extract_result_jsonl, write_document_html, write_reviewer_html


class PersonAttributes(BaseModel):
    role: str | None = None


class OrganizationAttributes(BaseModel):
    sector: str | None = None


request = ExtractRequest(
    documents=(
        "Alice Johnson is the CEO of Acme Robotics. "
        "Acme Robotics builds warehouse automation systems."
    ),
    task=ExtractionTask(
        instructions="Extract person and organization entities with useful attributes.",
        schema=EntitySchemaSet(
            entities=[
                EntitySpec(name="person", attributes_model=PersonAttributes),
                EntitySpec(name="organization", attributes_model=OrganizationAttributes),
            ]
        ),
        examples=[
            ExtractionExample(
                text="Bob is CTO at Nova Labs.",
                extractions=[
                    ExampleExtraction(entity="person", text="Bob", attributes={"role": "CTO"}),
                    ExampleExtraction(entity="organization", text="Nova Labs", attributes={"sector": "software"}),
                ],
            )
        ],
    ),
    options=ExtractOptions(max_passes=2, stop_when_no_new_extractions=True),
    runtime=RuntimeConfig(model="deepseek/deepseek-chat", temperature=0.0),
)

result = sourcery.extract(request)

output_dir = Path("output")
output_dir.mkdir(parents=True, exist_ok=True)

save_extract_result_jsonl(result, output_dir / "result.jsonl")
write_document_html(result.documents[0], output_dir / "document.viewer.html")
write_reviewer_html(result.documents[0], output_dir / "document.reviewer.html")

print("Run ID:", result.run_trace.run_id)
print("Documents:", result.metrics.documents_total)
print("Extractions:", result.metrics.extracted_total)
print("Warnings:", len(result.warnings))
```

## 2. Run It

```
uv run python quickstart.py
```

## 3. Inspect Outputs

- `output/result.jsonl`: machine-friendly output for downstream processing.
- `output/document.viewer.html`: span-highlighted read-only viewer.
- `output/document.reviewer.html`: interactive approve/reject review UI.

## Async Variant

```
result = await sourcery.aextract(request)
```

## What To Do Next

- Move to [Build A Pipeline](https://jolovicdev.github.io/sourcery/guides/build-a-pipeline/index.md) for mixed-source ingestion.
- Move to [Runtime And Tuning](https://jolovicdev.github.io/sourcery/guides/runtime-and-tuning/index.md) for reliability/throughput tuning.
