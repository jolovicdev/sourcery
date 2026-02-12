from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from sourcery.contracts import (
    AlignedExtraction,
    ChunkExtractionReport,
    ExtractionProvenance,
    ReconciliationConfig,
    RuntimeConfig,
    SessionRefinementConfig,
    SourceDocument,
    TextChunk,
)
from sourcery.exceptions import RuntimeIntegrationError
from sourcery.runtime.blackgeorge_runtime import BlackGeorgeRuntime


def _chunk(document_id: str, order_index: int, *, pass_id: int = 1) -> TextChunk:
    text = f"{document_id} chunk {order_index}"
    char_start = order_index * 20
    char_end = char_start + len(text)
    return TextChunk(
        chunk_id=f"{document_id}:p{pass_id}:c{order_index}",
        document_id=document_id,
        pass_id=pass_id,
        order_index=order_index,
        text=text,
        char_start=char_start,
        char_end=char_end,
    )


def _report(run_id: str, pass_id: int, chunk: TextChunk) -> ChunkExtractionReport:
    return ChunkExtractionReport(
        run_id=run_id,
        pass_id=pass_id,
        chunk=chunk,
        candidates=[],
        warnings=[],
        events=[],
        worker_name="ExtractorWorker",
        model="deepseek/deepseek-chat",
        raw_run_id="raw-run-id",
    )


def _aligned_extraction() -> AlignedExtraction:
    return AlignedExtraction(
        entity="concept",
        text="Transformer",
        attributes={"category": "architecture"},
        char_start=0,
        char_end=11,
        alignment_status="exact",
        provenance=ExtractionProvenance(
            run_id="run-1",
            pass_id=1,
            chunk_id="doc-1:p1:c0",
            worker_name="ExtractorWorker",
            model="deepseek/deepseek-chat",
        ),
    )


def test_run_pass_preserves_input_chunk_order_across_documents() -> None:
    runtime: Any = object.__new__(BlackGeorgeRuntime)
    chunks = [
        _chunk("doc-a", 0),
        _chunk("doc-a", 1),
        _chunk("doc-b", 0),
    ]

    runtime._build_refinement_contexts = lambda **_: {}
    runtime._chunk_batches = lambda batch_chunks, _batch_size: [list(batch_chunks)]

    def run_flow_batch(**kwargs: Any) -> list[ChunkExtractionReport]:
        return [
            _report(kwargs["run_id"], kwargs["pass_id"], chunk)
            for chunk in reversed(kwargs["chunks"])
        ]

    runtime._run_flow_batch = run_flow_batch

    reports = BlackGeorgeRuntime.run_pass(
        runtime,
        run_id="run-1",
        pass_id=1,
        chunks=chunks,
        task_instructions="Extract entities",
        batch_concurrency=4,
    )

    assert [report.chunk.chunk_id for report in reports] == [chunk.chunk_id for chunk in chunks]


class _FakeWorker:
    def __init__(self, *, name: str, instructions: str) -> None:
        self.name = name
        self.instructions = instructions


class _FakeSession:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id


class _FakeDesk:
    def __init__(self) -> None:
        self.session_calls: list[tuple[str, dict[str, Any]]] = []

    def session(self, worker: Any, *, session_id: str, metadata: dict[str, Any]) -> _FakeSession:
        self.session_calls.append((session_id, dict(metadata)))
        return _FakeSession(session_id)


def test_refinement_uses_isolated_session_per_document() -> None:
    runtime: Any = object.__new__(BlackGeorgeRuntime)
    runtime._runtime_config = RuntimeConfig(
        model="deepseek/deepseek-chat",
        session_refinement=SessionRefinementConfig(enabled=True, max_turns=1, context_chars=200),
    )
    runtime._blackgeorge = SimpleNamespace(Worker=_FakeWorker)
    fake_desk = _FakeDesk()
    runtime._desk = fake_desk
    runtime._provider_name = lambda: "deepseek"

    calls: list[tuple[str, str, str]] = []

    def run_session_with_retries(
        *, session: _FakeSession, payload: dict[str, Any], context: Any
    ) -> Any:
        calls.append((session.session_id, payload["document_id"], payload["chunk_id"]))
        return SimpleNamespace(
            data={"refinement_context": f"{payload['document_id']}::{payload['chunk_id']}"}
        )

    runtime._run_session_with_retries = run_session_with_retries

    chunks = [
        _chunk("doc-a", 1),
        _chunk("doc-b", 0),
        _chunk("doc-a", 0),
    ]

    contexts = BlackGeorgeRuntime._build_refinement_contexts(
        runtime,
        run_id="run-1",
        pass_id=1,
        chunks=chunks,
        task_instructions="Extract entities",
    )

    assert fake_desk.session_calls == [
        (
            "sourcery-refinement:run-1:p1:doc-a",
            {"run_id": "run-1", "pass_id": 1, "document_id": "doc-a"},
        ),
        (
            "sourcery-refinement:run-1:p1:doc-b",
            {"run_id": "run-1", "pass_id": 1, "document_id": "doc-b"},
        ),
    ]

    session_by_document = {
        metadata["document_id"]: session_id for session_id, metadata in fake_desk.session_calls
    }
    for session_id, document_id, _chunk_id in calls:
        assert session_id == session_by_document[document_id]

    assert set(contexts.keys()) == {chunk.chunk_id for chunk in chunks}


def test_refinement_invalid_response_schema_raises_runtime_integration_error() -> None:
    runtime: Any = object.__new__(BlackGeorgeRuntime)
    runtime._runtime_config = RuntimeConfig(
        model="deepseek/deepseek-chat",
        session_refinement=SessionRefinementConfig(enabled=True, max_turns=1, context_chars=200),
    )
    runtime._blackgeorge = SimpleNamespace(Worker=_FakeWorker)
    runtime._desk = _FakeDesk()
    runtime._provider_name = lambda: "deepseek"
    runtime._run_session_with_retries = lambda **_: SimpleNamespace(
        data={"refinement_context": {"invalid": "payload"}}
    )

    with pytest.raises(RuntimeIntegrationError):
        BlackGeorgeRuntime._build_refinement_contexts(
            runtime,
            run_id="run-1",
            pass_id=1,
            chunks=[_chunk("doc-a", 0)],
            task_instructions="Extract entities",
        )


def test_reconcile_document_falls_back_for_runtime_errors() -> None:
    runtime: Any = object.__new__(BlackGeorgeRuntime)
    runtime._runtime_config = RuntimeConfig(
        model="deepseek/deepseek-chat",
        reconciliation=ReconciliationConfig(enabled=True, use_workforce=True),
    )
    runtime._fallback_canonical_claims = lambda **_: []
    runtime._run_reconciliation_workforce = lambda **_: (_ for _ in ()).throw(
        RuntimeIntegrationError("retry exhausted")
    )

    result = BlackGeorgeRuntime.reconcile_document(
        runtime,
        run_id="run-1",
        document=SourceDocument(document_id="doc-1", text="Transformer"),
        extractions=[_aligned_extraction()],
        task_instructions="Extract entities",
    )

    assert result.warnings
    assert "RuntimeIntegrationError" in result.warnings[0]


def test_reconcile_document_propagates_unexpected_errors() -> None:
    runtime: Any = object.__new__(BlackGeorgeRuntime)
    runtime._runtime_config = RuntimeConfig(
        model="deepseek/deepseek-chat",
        reconciliation=ReconciliationConfig(enabled=True, use_workforce=True),
    )
    runtime._fallback_canonical_claims = lambda **_: []
    runtime._run_reconciliation_workforce = lambda **_: (_ for _ in ()).throw(
        ValueError("unexpected failure")
    )

    with pytest.raises(ValueError):
        BlackGeorgeRuntime.reconcile_document(
            runtime,
            run_id="run-1",
            document=SourceDocument(document_id="doc-1", text="Transformer"),
            extractions=[_aligned_extraction()],
            task_instructions="Extract entities",
        )
