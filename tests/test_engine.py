from __future__ import annotations

from sourcery.contracts import ExtractRequest
from sourcery.runtime.engine import SourceryEngine


def test_engine_extracts_with_fake_runtime(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    result = engine.extract(extract_request)

    assert len(result.documents) == 1
    assert len(result.documents[0].extractions) >= 2
    assert result.metrics.extracted_total >= 2
    assert result.metrics.passes_executed >= 1
    assert result.run_trace.chunk_ids


def test_engine_stops_when_no_new_extractions(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    extract_request.options.max_passes = 3
    extract_request.options.stop_when_no_new_extractions = True

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    result = engine.extract(extract_request)

    assert result.metrics.passes_executed < 3


def test_engine_async(extract_request: ExtractRequest) -> None:
    import asyncio
    from tests.conftest import FakeRuntime

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    result = asyncio.run(engine.aextract(extract_request))

    assert result.documents
    assert result.metrics.documents_total == 1


def test_engine_passes_batch_concurrency(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    extract_request.options.batch_concurrency = 3
    FakeRuntime.last_batch_concurrency = None

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    engine.extract(extract_request)

    assert FakeRuntime.last_batch_concurrency == 3


def test_engine_replay_run(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    replay, events = engine.replay_run(extract_request, "raw-run-1")

    assert replay is not None
    assert replay["run_id"] == "raw-run-1"
    assert events == []


def test_engine_runs_document_reconciliation(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeReconciliationRuntime

    extract_request.runtime.reconciliation.enabled = True
    FakeReconciliationRuntime.reconcile_called = False

    engine = SourceryEngine(runtime_factory=FakeReconciliationRuntime)
    result = engine.extract(extract_request)

    assert FakeReconciliationRuntime.reconcile_called is True
    assert len(result.documents[0].extractions) == 1
    assert result.documents[0].canonical_claims
