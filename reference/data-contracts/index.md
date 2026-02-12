# Data Contracts

All contracts are defined in `sourcery/contracts/models.py`.

## Request Contracts

- `EntitySpec`: entity name + Pydantic attributes model.
- `EntitySchemaSet`: unique list of entity specs.
- `ExtractionExample`: few-shot text and expected extractions.
- `ExtractionTask`: instructions + schema + examples + `strict_example_alignment`.
- `ExtractOptions`: deterministic pipeline controls.
- `RuntimeConfig`: model/runtime/retry/refinement/reconciliation settings.
- `ExtractRequest`: full extraction input.

`ExtractRequest.documents` accepts:

- `str` (single inline document), or
- `list[SourceDocument]`.

## Runtime/Pipeline Contracts

- `TextChunk`
- `ExtractionCandidate`
- `ChunkRuntimeInput`
- `ChunkExtractionReport`
- `PromptEnvelope`

## Result Contracts

- `AlignedExtraction`
- `CanonicalClaim`
- `DocumentResult`
- `DocumentReconciliationReport`
- `RunMetrics`
- `ExtractionRunTrace`
- `ExtractResult`

## Event Contracts

- `EventRecord`
- `ExtractionProvenance`

## Validation Guarantees

Contracts enforce:

- non-empty text and entity names,
- valid char/token offset ranges,
- unique schema entity names,
- non-empty `ExtractionTask.examples`,
- threshold bounds (`fuzzy_alignment_threshold`, retry/reconciliation limits),
- model route non-empty (`runtime.model`).

## Minimal Contract Example

```
from pydantic import BaseModel
from sourcery.contracts import EntitySchemaSet, EntitySpec

class CompanyAttrs(BaseModel):
    sector: str | None = None

schema = EntitySchemaSet(
    entities=[EntitySpec(name="company", attributes_model=CompanyAttrs)]
)
```
