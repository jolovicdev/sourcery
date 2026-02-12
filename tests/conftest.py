from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

import pytest
from pydantic import BaseModel

from sourcery.contracts import (
    AlignedExtraction,
    CanonicalClaim,
    ChunkExtractionReport,
    DocumentReconciliationReport,
    EventRecord,
    ExtractRequest,
    ExtractionCandidate,
    ExtractionExample,
    ExtractionTask,
    ExampleExtraction,
    RuntimeConfig,
    SourceDocument,
    TextChunk,
    EntitySchemaSet,
    EntitySpec,
)


class PersonAttributes(BaseModel):
    role: str


class OrganizationAttributes(BaseModel):
    industry: str


class FakeRuntime:
    last_batch_concurrency: int | None = None

    def __init__(
        self, runtime_config: RuntimeConfig, schema_set: EntitySchemaSet, prompt_compiler: Any
    ) -> None:
        self.runtime_config = runtime_config
        self.schema_set = schema_set
        self.prompt_compiler = prompt_compiler
        self.calls: list[tuple[int, list[str], int]] = []

    def run_pass(
        self,
        *,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
        batch_concurrency: int,
    ) -> list[ChunkExtractionReport]:
        FakeRuntime.last_batch_concurrency = batch_concurrency
        self.calls.append((pass_id, [chunk.chunk_id for chunk in chunks], batch_concurrency))
        reports: list[ChunkExtractionReport] = []
        for chunk in chunks:
            candidates: list[ExtractionCandidate] = []
            if "Alice" in chunk.text:
                candidates.append(
                    ExtractionCandidate(
                        entity="person",
                        text="Alice",
                        attributes={"role": "CEO"},
                        confidence=0.97,
                    )
                )
            if "Acme" in chunk.text:
                candidates.append(
                    ExtractionCandidate(
                        entity="organization",
                        text="Acme",
                        attributes={"industry": "software"},
                        confidence=0.91,
                    )
                )
            report = ChunkExtractionReport(
                run_id=run_id,
                pass_id=pass_id,
                chunk=chunk,
                candidates=candidates,
                warnings=[],
                events=[
                    EventRecord(
                        event_id=f"e-{pass_id}-{chunk.order_index}",
                        type="worker.completed",
                        timestamp=datetime.now(timezone.utc),
                        run_id=run_id,
                        source="ExtractorWorker",
                        payload={"chunk_id": chunk.chunk_id},
                    )
                ],
                worker_name="ExtractorWorker",
                model=self.runtime_config.model,
                raw_run_id=f"bg-{run_id}-{pass_id}",
            )
            reports.append(report)
        return reports

    async def arun_pass(
        self,
        *,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
        batch_concurrency: int,
    ) -> list[ChunkExtractionReport]:
        return self.run_pass(
            run_id=run_id,
            pass_id=pass_id,
            chunks=chunks,
            task_instructions=task_instructions,
            batch_concurrency=batch_concurrency,
        )

    def replay_run(self, raw_run_id: str) -> tuple[dict[str, Any] | None, list[EventRecord]]:
        return {"run_id": raw_run_id, "status": "completed"}, []


class FakeReconciliationRuntime(FakeRuntime):
    reconcile_called = False

    def reconcile_document(
        self,
        *,
        run_id: str,
        document: SourceDocument,
        extractions: Sequence[AlignedExtraction],
        task_instructions: str,
    ) -> DocumentReconciliationReport:
        FakeReconciliationRuntime.reconcile_called = True
        reconciled = list(extractions[:1]) if extractions else []
        claims: list[CanonicalClaim] = []
        if reconciled:
            claims.append(
                CanonicalClaim(
                    claim_id=f"{document.document_id}:claim:0",
                    entity=reconciled[0].entity,
                    canonical_text=reconciled[0].text,
                    mention_count=1,
                    extraction_indices=[0],
                    confidence=reconciled[0].confidence,
                    attributes={"source": "fake-reconciler"},
                )
            )
        return DocumentReconciliationReport(
            document_id=document.document_id,
            reconciled_extractions=reconciled,
            canonical_claims=claims,
        )


@pytest.fixture
def task() -> ExtractionTask:
    return ExtractionTask(
        instructions="Extract entities.",
        schema=EntitySchemaSet(
            entities=[
                EntitySpec(name="person", attributes_model=PersonAttributes),
                EntitySpec(name="organization", attributes_model=OrganizationAttributes),
            ]
        ),
        examples=[
            ExtractionExample(
                text="Alice works at Acme.",
                extractions=[
                    ExampleExtraction(entity="person", text="Alice", attributes={"role": "CEO"}),
                    ExampleExtraction(
                        entity="organization",
                        text="Acme",
                        attributes={"industry": "software"},
                    ),
                ],
            )
        ],
    )


@pytest.fixture
def extract_request(task: ExtractionTask) -> ExtractRequest:
    return ExtractRequest(
        documents=[SourceDocument(document_id="doc-1", text="Alice is the CEO of Acme.")],
        task=task,
        runtime=RuntimeConfig(model="openai/gpt-5-nano"),
    )
