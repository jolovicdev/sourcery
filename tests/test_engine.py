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


def test_sync_async_produce_same_extractions(extract_request: ExtractRequest) -> None:
    import asyncio
    from tests.conftest import FakeRuntime

    sync_engine = SourceryEngine(runtime_factory=FakeRuntime)
    sync_result = sync_engine.extract(extract_request)

    FakeRuntime.last_batch_concurrency = None
    async_engine = SourceryEngine(runtime_factory=FakeRuntime)
    async_result = asyncio.run(async_engine.aextract(extract_request))

    assert sync_result.metrics.extracted_total == async_result.metrics.extracted_total
    assert sync_result.metrics.passes_executed == async_result.metrics.passes_executed
    assert sync_result.metrics.candidates_total == async_result.metrics.candidates_total
    assert sync_result.metrics.chunks_total == async_result.metrics.chunks_total
    assert len(sync_result.documents) == len(async_result.documents)
    for s_doc, a_doc in zip(sync_result.documents, async_result.documents):
        assert s_doc.document_id == a_doc.document_id
        assert [e.entity for e in s_doc.extractions] == [e.entity for e in a_doc.extractions]
        assert [e.text for e in s_doc.extractions] == [e.text for e in a_doc.extractions]


def test_streaming_yields_extraction_chunk_and_pass_events(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime
    from sourcery.contracts import StreamExtractionAdded, StreamChunkDone, StreamPassDone

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    gen = engine.extract_stream(extract_request)

    events: list[object] = []
    final: object = None
    try:
        while True:
            events.append(next(gen))
    except StopIteration as exc:
        final = exc.value

    assert any(isinstance(e, StreamExtractionAdded) for e in events)
    assert any(isinstance(e, StreamChunkDone) for e in events)
    assert any(isinstance(e, StreamPassDone) for e in events)
    assert final is not None
    from sourcery.contracts import ExtractResult
    assert isinstance(final, ExtractResult)
    assert final.metrics.extracted_total > 0


def test_streaming_uses_batch_concurrency_one(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    extract_request.options.batch_concurrency = 8
    FakeRuntime.last_batch_concurrency = None

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    gen = engine.extract_stream(extract_request)
    try:
        while True:
            next(gen)
    except StopIteration:
        pass

    assert FakeRuntime.last_batch_concurrency == 1


def test_async_reconciliation_uses_async_path(extract_request: ExtractRequest) -> None:
    import asyncio
    from tests.conftest import FakeReconciliationRuntime

    extract_request.runtime.reconciliation.enabled = True
    FakeReconciliationRuntime.reconcile_called = False
    FakeReconciliationRuntime.areconcile_called = False

    engine = SourceryEngine(runtime_factory=FakeReconciliationRuntime)
    asyncio.run(engine.aextract(extract_request))

    assert FakeReconciliationRuntime.areconcile_called is True


def test_refactored_metrics_invariants(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    result = engine.extract(extract_request)

    assert result.metrics.chunks_total > 0
    assert result.metrics.candidates_total >= result.metrics.extracted_total
    assert result.metrics.unresolved_total >= 0
    assert result.metrics.passes_executed >= 1
    assert result.metrics.documents_total == 1
    assert result.run_trace.chunk_ids
    assert len(result.run_trace.pass_ids) == result.metrics.passes_executed
    assert result.run_trace.run_id
    assert result.run_trace.model == extract_request.runtime.model


def test_custom_dependencies_are_invoked(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime
    from sourcery.contracts import EngineDependencies
    from sourcery.observability.trace import RunTraceCollector
    from sourcery.pipeline import PromptCompiler, ExampleValidator, align_candidates, merge_non_overlapping, plan_chunks

    planner_called: list[bool] = []
    aligner_called: list[bool] = []
    merger_called: list[bool] = []

    def tracking_planner(*args, **kwargs):
        planner_called.append(True)
        return plan_chunks(*args, **kwargs)

    def tracking_aligner(*args, **kwargs):
        aligner_called.append(True)
        return align_candidates(*args, **kwargs)

    def tracking_merger(*args, **kwargs):
        merger_called.append(True)
        return merge_non_overlapping(*args, **kwargs)

    deps = EngineDependencies(
        runtime_factory=FakeRuntime,
        prompt_compiler=PromptCompiler(),
        example_validator=ExampleValidator(),
        chunk_planner=tracking_planner,
        aligner=tracking_aligner,
        merger=tracking_merger,
        trace_collector_factory=RunTraceCollector,
    )

    engine = SourceryEngine(dependencies=deps)
    engine.extract(extract_request)

    assert len(planner_called) > 0, "chunk_planner was never called"
    assert len(aligner_called) > 0, "aligner was never called"
    assert len(merger_called) > 0, "merger was never called"
