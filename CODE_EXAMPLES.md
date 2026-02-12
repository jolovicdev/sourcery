# CODE_EXAMPLES.md

Practical examples for the current Sourcery API.

## 1) Minimal typed extraction

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
        instructions="Extract people and their role.",
        schema=EntitySchemaSet(
            entities=[EntitySpec(name="person", attributes_model=PersonAttrs)]
        ),
        examples=[
            ExtractionExample(
                text="Bob is the CTO.",
                extractions=[
                    ExampleExtraction(
                        entity="person",
                        text="Bob",
                        attributes={"role": "CTO"},
                    )
                ],
            )
        ],
    ),
    runtime=RuntimeConfig(model="deepseek/deepseek-chat"),
)

result = sourcery.extract(request)
print(result.metrics.model_dump(mode="json"))
print(result.documents[0].extractions)
```

## 2) Multi-entity extraction with options

```python
from pydantic import BaseModel

import sourcery
from sourcery.contracts import (
    EntitySchemaSet,
    EntitySpec,
    ExtractOptions,
    ExtractRequest,
    ExtractionExample,
    ExtractionTask,
    ExampleExtraction,
    RuntimeConfig,
    SourceDocument,
)


class PersonAttrs(BaseModel):
    role: str | None = None


class OrgAttrs(BaseModel):
    industry: str | None = None


request = ExtractRequest(
    documents=[
        SourceDocument(document_id="doc-1", text="Alice joined Acme as CEO."),
        SourceDocument(document_id="doc-2", text="Bob became CTO at Globex."),
    ],
    task=ExtractionTask(
        instructions="Extract people and organizations.",
        schema=EntitySchemaSet(
            entities=[
                EntitySpec(name="person", attributes_model=PersonAttrs),
                EntitySpec(name="organization", attributes_model=OrgAttrs),
            ]
        ),
        examples=[
            ExtractionExample(
                text="Carol works at Initech.",
                extractions=[
                    ExampleExtraction(entity="person", text="Carol", attributes={"role": None}),
                    ExampleExtraction(
                        entity="organization",
                        text="Initech",
                        attributes={"industry": None},
                    ),
                ],
            )
        ],
    ),
    options=ExtractOptions(
        max_chunk_chars=900,
        max_passes=2,
        batch_concurrency=8,
        fuzzy_alignment_threshold=0.82,
        stop_when_no_new_extractions=True,
    ),
    runtime=RuntimeConfig(model="deepseek/deepseek-chat"),
)

result = sourcery.extract(request)
for doc in result.documents:
    print(doc.document_id, len(doc.extractions), len(doc.canonical_claims))
```

## 3) Extract directly from sources (text/file/PDF/HTML/URL)

```python
from pathlib import Path
from pydantic import BaseModel

import sourcery
from sourcery.contracts import (
    EntitySchemaSet,
    EntitySpec,
    ExtractionExample,
    ExtractionTask,
    ExampleExtraction,
    RuntimeConfig,
)


class ClaimAttrs(BaseModel):
    category: str | None = None


task = ExtractionTask(
    instructions="Extract factual claims.",
    schema=EntitySchemaSet(
        entities=[EntitySpec(name="claim", attributes_model=ClaimAttrs)]
    ),
    examples=[
        ExtractionExample(
            text="Revenue increased in 2025.",
            extractions=[
                ExampleExtraction(
                    entity="claim",
                    text="Revenue increased in 2025",
                    attributes={"category": "finance"},
                )
            ],
        )
    ],
)

result = sourcery.extract_from_sources(
    [
        "Inline text source",
        Path("./docs/input.txt"),
        Path("./docs/report.pdf"),
        Path("./docs/page.html"),
        "https://example.com/report",
    ],
    task=task,
    runtime=RuntimeConfig(model="deepseek/deepseek-chat"),
)

print(result.metrics.documents_total)
```

Notes:
- PDF ingestion requires `pypdf`.
- OCR image ingestion requires `pillow` and `pytesseract`.

## 4) Async extraction

```python
import asyncio
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


async def main() -> None:
    request = ExtractRequest(
        documents="Dana is VP Engineering.",
        task=ExtractionTask(
            instructions="Extract people.",
            schema=EntitySchemaSet(
                entities=[EntitySpec(name="person", attributes_model=PersonAttrs)]
            ),
            examples=[
                ExtractionExample(
                    text="Eve is CFO.",
                    extractions=[
                        ExampleExtraction(entity="person", text="Eve", attributes={"role": "CFO"})
                    ],
                )
            ],
        ),
        runtime=RuntimeConfig(model="deepseek/deepseek-chat"),
    )
    result = await sourcery.aextract(request)
    print(result.metrics.extracted_total)


asyncio.run(main())
```

## 5) Reliability controls: retry, session refinement, reconciliation

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
    ReconciliationConfig,
    RetryPolicy,
    RuntimeConfig,
    SessionRefinementConfig,
)


class EventAttrs(BaseModel):
    severity: str | None = None


request = ExtractRequest(
    documents="Outage started at 09:10 UTC. Service recovered at 09:42 UTC.",
    task=ExtractionTask(
        instructions="Extract operational events.",
        schema=EntitySchemaSet(
            entities=[EntitySpec(name="event", attributes_model=EventAttrs)]
        ),
        examples=[
            ExtractionExample(
                text="Incident started at 10:00.",
                extractions=[
                    ExampleExtraction(
                        entity="event",
                        text="Incident started at 10:00",
                        attributes={"severity": "high"},
                    )
                ],
            )
        ],
    ),
    runtime=RuntimeConfig(
        model="deepseek/deepseek-chat",
        retry=RetryPolicy(
            max_attempts=4,
            initial_backoff_seconds=0.8,
            max_backoff_seconds=10.0,
            backoff_multiplier=2.0,
            retry_on_rate_limit=True,
            retry_on_transient_errors=True,
            auto_resume_paused_runs=True,
            max_pause_resumes=5,
        ),
        session_refinement=SessionRefinementConfig(
            enabled=True,
            max_turns=2,
            context_chars=400,
        ),
        reconciliation=ReconciliationConfig(
            enabled=True,
            use_workforce=True,
            min_mentions_for_claim=1,
            max_claims=100,
        ),
    ),
)

result = sourcery.extract(request)
print(result.warnings)
```

## 6) Save/load JSONL + reviewer HTML

```python
from pathlib import Path
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
from sourcery.io import load_document_results_jsonl, save_extract_result_jsonl, write_reviewer_html


class PersonAttrs(BaseModel):
    role: str | None = None


request = ExtractRequest(
    documents="Alice is CEO. Bob is CTO.",
    task=ExtractionTask(
        instructions="Extract people.",
        schema=EntitySchemaSet(
            entities=[EntitySpec(name="person", attributes_model=PersonAttrs)]
        ),
        examples=[
            ExtractionExample(
                text="Carol is CFO.",
                extractions=[
                    ExampleExtraction(entity="person", text="Carol", attributes={"role": "CFO"})
                ],
            )
        ],
    ),
    runtime=RuntimeConfig(model="deepseek/deepseek-chat"),
)

result = sourcery.extract(request)

out_dir = Path("./output")
out_dir.mkdir(parents=True, exist_ok=True)

jsonl_path = out_dir / "result.jsonl"
html_path = out_dir / "reviewer.html"

save_extract_result_jsonl(result, jsonl_path)
loaded_docs = load_document_results_jsonl(jsonl_path)
write_reviewer_html(loaded_docs[0], html_path, title="Extraction Review")

print(jsonl_path, html_path)
```

## 7) Notebook/HTML visualization

```python
from sourcery.io import visualize

# From JSONL path (returns HTML object in notebook, raw HTML string otherwise)
content = visualize("./output/result.jsonl", animation_speed=0.8, show_legend=True)
print(type(content))
```

## 8) Replay a BlackGeorge run from provenance

```python
from pydantic import BaseModel

from sourcery.contracts import (
    EntitySchemaSet,
    EntitySpec,
    ExtractRequest,
    ExtractionExample,
    ExtractionTask,
    ExampleExtraction,
    RuntimeConfig,
)
from sourcery.runtime import SourceryEngine


class PersonAttrs(BaseModel):
    role: str | None = None


engine = SourceryEngine()
request = ExtractRequest(
    documents="Alice is CEO.",
    task=ExtractionTask(
        instructions="Extract people.",
        schema=EntitySchemaSet(
            entities=[EntitySpec(name="person", attributes_model=PersonAttrs)]
        ),
        examples=[
            ExtractionExample(
                text="Bob is CTO.",
                extractions=[
                    ExampleExtraction(entity="person", text="Bob", attributes={"role": "CTO"})
                ],
            )
        ],
    ),
    runtime=RuntimeConfig(model="deepseek/deepseek-chat"),
)

result = engine.extract(request)

raw_run_id = None
for doc in result.documents:
    for extraction in doc.extractions:
        if extraction.provenance.raw_run_id:
            raw_run_id = extraction.provenance.raw_run_id
            break
    if raw_run_id:
        break

if raw_run_id:
    replay_payload, replay_events = engine.replay_run(request, raw_run_id)
    print(replay_payload)
    print(len(replay_events))
```

## 9) Error handling with typed exceptions

```python
from sourcery.exceptions import (
    ExampleValidationError,
    SourceryProviderError,
    SourceryRateLimitError,
    SourceryRetryExhaustedError,
)

try:
    # call sourcery.extract(...)
    pass
except ExampleValidationError as exc:
    print("Example alignment failed:", exc)
except SourceryRateLimitError as exc:
    print("Provider rate-limited:", exc)
except SourceryRetryExhaustedError as exc:
    print("Retries exhausted after", exc.attempts, "attempts")
except SourceryProviderError as exc:
    print("Provider/runtime error:", exc)
```

## 10) Benchmark command

```bash
uv run sourcery-benchmark \
  --text-types english,japanese,french,spanish \
  --max-chars 4500 \
  --max-passes 2 \
  --batch-concurrency 4 \
  --sourcery-model deepseek/deepseek-chat
```

Compatibility wrapper:

```bash
uv run benchmark_compare.py --text-types english
```
