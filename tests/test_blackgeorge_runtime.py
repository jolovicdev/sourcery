from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from blackgeorge.adapters.base import BaseModelAdapter
from pydantic import BaseModel

from sourcery.contracts import (
    AlignedExtraction,
    EntitySchemaSet,
    EntitySpec,
    ExtractionProvenance,
    ReconciliationConfig,
    RetryPolicy,
    RuntimeConfig,
    SessionRefinementConfig,
    SourceDocument,
    TextChunk,
)
from sourcery.pipeline.prompt_compiler import PromptCompiler
from sourcery.runtime.blackgeorge_models import SessionRefinementResult
from sourcery.runtime.blackgeorge_runtime import BlackGeorgeRuntime


class PersonAttributes(BaseModel):
    role: str


class DeterministicAdapter(BaseModelAdapter):
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.schemas: list[str] = []

    def structured_complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_schema: Any,
        retries: int,
    ) -> Any:
        self.schemas.append(response_schema.__name__)
        if self.failures:
            self.failures -= 1
            raise TimeoutError("temporary timeout")
        if response_schema is SessionRefinementResult:
            return response_schema(refinement_context="Earlier context")
        return response_schema(extractions=[])

    async def astructured_complete(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_schema: Any,
        retries: int,
    ) -> Any:
        return self.structured_complete(
            model=model,
            messages=messages,
            response_schema=response_schema,
            retries=retries,
        )


def make_runtime(
    storage_dir: Path,
    *,
    retry: RetryPolicy | None = None,
    refinement: SessionRefinementConfig | None = None,
    reconciliation: ReconciliationConfig | None = None,
) -> BlackGeorgeRuntime:
    config = RuntimeConfig(
        model="test/model",
        storage_dir=str(storage_dir),
        retry=retry or RetryPolicy(),
        session_refinement=refinement or SessionRefinementConfig(),
        reconciliation=reconciliation or ReconciliationConfig(),
    )
    schema = EntitySchemaSet(
        entities=[EntitySpec(name="person", attributes_model=PersonAttributes)]
    )
    return BlackGeorgeRuntime(config, schema, PromptCompiler())


def chunk(document_id: str, order_index: int) -> TextChunk:
    text = f"{document_id} chunk {order_index}"
    char_start = order_index * 20
    return TextChunk(
        chunk_id=f"{document_id}:p1:c{order_index}",
        document_id=document_id,
        pass_id=1,
        order_index=order_index,
        text=text,
        char_start=char_start,
        char_end=char_start + len(text),
    )


def extraction(text: str, start: int, confidence: float) -> AlignedExtraction:
    return AlignedExtraction(
        entity="person",
        text=text,
        attributes={"role": "researcher"},
        char_start=start,
        char_end=start + len(text),
        alignment_status="exact",
        confidence=confidence,
        provenance=ExtractionProvenance(
            run_id="run-1",
            pass_id=1,
            chunk_id="doc-1:p1:c0",
            worker_name="ExtractorWorker",
            model="test/model",
        ),
    )


def test_run_pass_uses_blackgeorge_flow_retries_and_keeps_input_order(
    tmp_path: Path,
) -> None:
    runtime = make_runtime(
        tmp_path,
        retry=RetryPolicy(
            max_attempts=2,
            initial_backoff_seconds=0,
            max_backoff_seconds=0,
        ),
    )
    adapter = DeterministicAdapter(failures=1)
    runtime._desk.adapter = adapter
    chunks = [chunk("doc-a", 0), chunk("doc-a", 1), chunk("doc-b", 0)]

    try:
        reports = runtime.run_pass(
            run_id="run-1",
            pass_id=1,
            chunks=chunks,
            task_instructions="Extract people",
            batch_concurrency=3,
        )
    finally:
        runtime.close()

    assert [report.chunk.chunk_id for report in reports] == [item.chunk_id for item in chunks]
    assert len({report.worker_name for report in reports}) == len(chunks)
    assert len(adapter.schemas) == 6
    assert any(event.type == "run.completed" for report in reports for event in report.events)
    assert any(event.type == "run.failed" for report in reports for event in report.events)


def test_async_pass_runs_session_refinement_without_sync_event_loop_calls(
    tmp_path: Path,
) -> None:
    runtime = make_runtime(
        tmp_path,
        refinement=SessionRefinementConfig(enabled=True, max_turns=1, context_chars=200),
    )
    adapter = DeterministicAdapter()
    runtime._desk.adapter = adapter

    try:
        reports = asyncio.run(
            runtime.arun_pass(
                run_id="run-1",
                pass_id=1,
                chunks=[chunk("doc-a", 1), chunk("doc-b", 0), chunk("doc-a", 0)],
                task_instructions="Extract people",
                batch_concurrency=3,
            )
        )
    finally:
        runtime.close()

    assert len(reports) == 3
    assert adapter.schemas.count("SessionRefinementResult") == 3
    assert any(event.type == "run.completed" for event in reports[0].events)


def test_reconciliation_claim_limit_counts_accepted_claims(tmp_path: Path) -> None:
    runtime = make_runtime(
        tmp_path,
        reconciliation=ReconciliationConfig(
            enabled=True,
            use_workforce=False,
            min_mentions_for_claim=2,
            max_claims=1,
        ),
    )
    extractions = [
        extraction("Alice", 0, 0.9),
        extraction("Transformer", 10, 0.8),
        extraction("Transformer", 30, 1.0),
    ]

    try:
        result = runtime.reconcile_document(
            run_id="run-1",
            document=SourceDocument(document_id="doc-1", text="Alice Transformer Transformer"),
            extractions=extractions,
            task_instructions="Extract people",
        )
    finally:
        runtime.close()

    assert len(result.canonical_claims) == 1
    assert result.canonical_claims[0].canonical_text == "Transformer"
    assert result.canonical_claims[0].extraction_indices == [1, 2]
    assert result.canonical_claims[0].confidence == 0.9
