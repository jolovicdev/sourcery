# Build A Pipeline

This guide shows a production-oriented extraction workflow from mixed sources to review output.

## 1. Define Entity Schemas

```python
from pydantic import BaseModel

class PersonAttrs(BaseModel):
    role: str | None = None

class CompanyAttrs(BaseModel):
    industry: str | None = None
```

## 2. Build Task and Examples

```python
from sourcery.contracts import EntitySchemaSet, EntitySpec, ExtractionExample, ExtractionTask, ExampleExtraction

task = ExtractionTask(
    instructions="Extract people and companies mentioned in the text.",
    schema=EntitySchemaSet(
        entities=[
            EntitySpec(name="person", attributes_model=PersonAttrs),
            EntitySpec(name="company", attributes_model=CompanyAttrs),
        ]
    ),
    examples=[
        ExtractionExample(
            text="Ada is CEO at ByteWorks.",
            extractions=[
                ExampleExtraction(entity="person", text="Ada", attributes={"role": "CEO"}),
                ExampleExtraction(entity="company", text="ByteWorks", attributes={"industry": "software"}),
            ],
        )
    ],
    strict_example_alignment=True,
)
```

## 3. Run from Mixed Sources

```python
import sourcery
from sourcery.contracts import ExtractOptions, ExtractRequest, RuntimeConfig
from sourcery.ingest import load_source_documents

sources = [
    "docs/input/report.pdf",
    "https://example.com/news/article",
    "Inline note: Helen joined Orbit Labs as COO.",
]
runtime = RuntimeConfig(model="deepseek/deepseek-chat", temperature=0.0)
options = ExtractOptions(
    max_chunk_chars=1200,
    max_passes=2,
    stop_when_no_new_extractions=True,
    allow_unresolved=False,
)
request = ExtractRequest(
    documents=load_source_documents(sources),
    task=task,
    runtime=runtime,
    options=options,
)
result = sourcery.extract(request)
```

## 4. Persist and Review

```python
from pathlib import Path
from sourcery.io import save_extract_result_jsonl, write_document_html, write_reviewer_html

output = Path("output")
output.mkdir(parents=True, exist_ok=True)

save_extract_result_jsonl(result, output / "result.jsonl")
for index, document in enumerate(result.documents):
    write_document_html(document, output / f"doc-{index}.viewer.html")
    write_reviewer_html(document, output / f"doc-{index}.reviewer.html")
```

## 5. Inspect Metrics and Warnings

```python
print(result.metrics.model_dump(mode="json"))
for warning in result.warnings:
    print("warning:", warning)
```

## 6. Replay Raw Runtime Runs (Optional)

```python
from sourcery.runtime import SourceryEngine

engine = SourceryEngine()
raw_run_id = None
if result.documents and result.documents[0].extractions:
    raw_run_id = result.documents[0].extractions[0].provenance.raw_run_id

if raw_run_id is not None:
    replay_payload, replay_events = engine.replay_run(request, raw_run_id)
```

Use replay for provider debugging, audits, or incident postmortems.
