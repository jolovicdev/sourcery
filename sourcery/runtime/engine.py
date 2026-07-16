from __future__ import annotations

from collections import defaultdict
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Callable, Union

from sourcery.contracts import (
    AlignedExtraction,
    ChunkExtractionReport,
    DocumentResult,
    EngineDependencies,
    EventRecord,
    ExtractRequest,
    ExtractResult,
    ExtractionProvenance,
    RunMetrics,
    SourceDocument,
    StreamChunkDone,
    StreamExtractionAdded,
    StreamPassDone,
    TextChunk,
    new_run_id,
    utc_now,
)
from sourcery.exceptions import RuntimeIntegrationError
from sourcery.observability.trace import RunTraceCollector
from sourcery.pipeline import (
    ExampleValidator,
    PromptCompiler,
    align_candidates,
    merge_non_overlapping,
    plan_chunks,
)
from sourcery.runtime.base import (
    AsyncDocumentReconciliationRuntime,
    ChunkRuntime,
    ClosableRuntime,
    DocumentReconciliationRuntime,
)
from sourcery.runtime.blackgeorge_runtime import BlackGeorgeRuntime


@dataclass
class EngineRunState:
    run_id: str
    documents: list[SourceDocument]
    runtime: ChunkRuntime
    reconciliation_runtime: DocumentReconciliationRuntime | None
    async_reconciliation_runtime: AsyncDocumentReconciliationRuntime | None
    metrics: RunMetrics
    trace_collector: RunTraceCollector
    warnings: list[str]
    document_extractions: dict[str, list[AlignedExtraction]] = field(
        default_factory=lambda: defaultdict(list)
    )
    pass_count: int = 0
    total_candidates: int = 0
    unresolved_total: int = 0
    chunk_ids: list[str] = field(default_factory=list)


class SourceryEngine:
    def __init__(
        self,
        *,
        runtime_factory: Callable[..., ChunkRuntime] = BlackGeorgeRuntime,
        dependencies: EngineDependencies | None = None,
    ) -> None:
        self._runtime_factory = runtime_factory
        if dependencies is None:
            self._prompt_compiler = PromptCompiler()
            self._example_validator = ExampleValidator()
            self._trace_collector_factory = RunTraceCollector
            self._chunk_planner = plan_chunks
            self._aligner = align_candidates
            self._merger = merge_non_overlapping
        else:
            self._prompt_compiler = dependencies.prompt_compiler
            self._example_validator = dependencies.example_validator
            self._trace_collector_factory = dependencies.trace_collector_factory
            self._runtime_factory = dependencies.runtime_factory
            self._chunk_planner = dependencies.chunk_planner
            self._aligner = dependencies.aligner
            self._merger = dependencies.merger

    def extract(self, request: ExtractRequest) -> ExtractResult:
        state = self._start_run(request)
        try:
            for pass_id in range(1, request.options.max_passes + 1):
                chunks = self._plan_pass(state, request, pass_id)
                reports = state.runtime.run_pass(
                    run_id=state.run_id,
                    pass_id=pass_id,
                    chunks=chunks,
                    task_instructions=request.task.instructions,
                    batch_concurrency=request.options.batch_concurrency,
                )
                self._validate_reports(
                    run_id=state.run_id,
                    pass_id=pass_id,
                    chunks=chunks,
                    reports=reports,
                )
                additions = sum(self._process_report(state, report, request) for report in reports)
                if request.options.stop_when_no_new_extractions and additions == 0:
                    break
            return self._finalize(state, request)
        finally:
            self._close_runtime(state.runtime)

    async def aextract(self, request: ExtractRequest) -> ExtractResult:
        state = self._start_run(request)
        try:
            for pass_id in range(1, request.options.max_passes + 1):
                chunks = self._plan_pass(state, request, pass_id)
                reports = await state.runtime.arun_pass(
                    run_id=state.run_id,
                    pass_id=pass_id,
                    chunks=chunks,
                    task_instructions=request.task.instructions,
                    batch_concurrency=request.options.batch_concurrency,
                )
                self._validate_reports(
                    run_id=state.run_id,
                    pass_id=pass_id,
                    chunks=chunks,
                    reports=reports,
                )
                additions = sum(self._process_report(state, report, request) for report in reports)
                if request.options.stop_when_no_new_extractions and additions == 0:
                    break
            return await self._finalize_async(state, request)
        finally:
            self._close_runtime(state.runtime)

    StreamEvent = Union[StreamExtractionAdded, StreamChunkDone, StreamPassDone]

    def extract_stream(
        self, request: ExtractRequest
    ) -> Generator[StreamEvent, None, ExtractResult]:
        state = self._start_run(request)
        try:
            for pass_id in range(1, request.options.max_passes + 1):
                chunks = self._plan_pass(state, request, pass_id)
                additions = 0

                batch_size = request.options.batch_concurrency
                for batch_start in range(0, len(chunks), batch_size):
                    batch = chunks[batch_start : batch_start + batch_size]
                    reports = state.runtime.run_pass(
                        run_id=state.run_id,
                        pass_id=pass_id,
                        chunks=batch,
                        task_instructions=request.task.instructions,
                        batch_concurrency=batch_size,
                    )
                    self._validate_reports(
                        run_id=state.run_id,
                        pass_id=pass_id,
                        chunks=batch,
                        reports=reports,
                    )
                    reports_by_chunk = {report.chunk.chunk_id: report for report in reports}
                    for chunk in batch:
                        report = reports_by_chunk[chunk.chunk_id]
                        document_id = report.chunk.document_id
                        previous_ids = {
                            id(extraction) for extraction in state.document_extractions[document_id]
                        }
                        additions += self._process_report(state, report, request)
                        for extraction in state.document_extractions[document_id]:
                            if id(extraction) not in previous_ids:
                                yield StreamExtractionAdded(
                                    document_id=document_id,
                                    extraction=extraction,
                                )
                        yield StreamChunkDone(
                            chunk_id=report.chunk.chunk_id,
                            document_id=document_id,
                            pass_id=pass_id,
                            candidates_found=len(report.candidates),
                        )

                yield StreamPassDone(
                    pass_id=pass_id,
                    additions_this_pass=additions,
                    extractions_so_far=sum(
                        len(extractions) for extractions in state.document_extractions.values()
                    ),
                )
                if request.options.stop_when_no_new_extractions and additions == 0:
                    break

            return self._finalize(state, request)
        finally:
            self._close_runtime(state.runtime)

    def replay_run(
        self, request: ExtractRequest, raw_run_id: str
    ) -> tuple[dict[str, object] | None, list[EventRecord]]:
        runtime = self._make_runtime(request)
        try:
            replay, events = runtime.replay_run(raw_run_id)
            return replay, events
        finally:
            self._close_runtime(runtime)

    def _make_runtime(self, request: ExtractRequest) -> ChunkRuntime:
        prompt_compiler = self._prompt_compiler
        if isinstance(prompt_compiler, PromptCompiler):
            prompt_compiler = prompt_compiler.with_examples(request.task.examples)
        return self._runtime_factory(
            request.runtime,
            request.task.entity_schema,
            prompt_compiler,
        )

    def _close_runtime(self, runtime: ChunkRuntime) -> None:
        if isinstance(runtime, ClosableRuntime):
            runtime.close()

    def _start_run(self, request: ExtractRequest) -> EngineRunState:
        run_id = new_run_id()
        documents = request.normalize_documents()

        issues = self._example_validator.validate(
            task=request.task,
            fuzzy_threshold=request.options.fuzzy_alignment_threshold,
        )
        warnings: list[str] = []
        warnings.extend(self._example_validator.enforce_or_warn(task=request.task, issues=issues))

        metrics = RunMetrics(
            documents_total=len(documents),
            started_at=utc_now(),
        )
        trace_collector = self._trace_collector_factory(run_id=run_id, model=request.runtime.model)
        runtime = self._make_runtime(request)
        reconciliation_runtime: DocumentReconciliationRuntime | None = None
        async_reconciliation_runtime: AsyncDocumentReconciliationRuntime | None = None
        if isinstance(runtime, DocumentReconciliationRuntime):
            reconciliation_runtime = runtime
        if isinstance(runtime, AsyncDocumentReconciliationRuntime):
            async_reconciliation_runtime = runtime

        return EngineRunState(
            run_id=run_id,
            documents=documents,
            runtime=runtime,
            reconciliation_runtime=reconciliation_runtime,
            async_reconciliation_runtime=async_reconciliation_runtime,
            metrics=metrics,
            trace_collector=trace_collector,
            warnings=warnings,
        )

    def _plan_pass(
        self, state: EngineRunState, request: ExtractRequest, pass_id: int
    ) -> list[TextChunk]:
        state.pass_count = pass_id
        chunks = self._chunk_planner(
            state.documents,
            pass_id=pass_id,
            max_chunk_chars=request.options.max_chunk_chars,
            context_window_chars=request.options.context_window_chars,
        )
        state.chunk_ids.extend(chunk.chunk_id for chunk in chunks)
        state.metrics.chunks_total += len(chunks)
        return chunks

    def _process_report(
        self,
        state: EngineRunState,
        report: ChunkExtractionReport,
        request: ExtractRequest,
    ) -> int:
        state.trace_collector.add_report_events(report)
        state.total_candidates += len(report.candidates)

        provenance = ExtractionProvenance(
            run_id=state.run_id,
            pass_id=report.pass_id,
            chunk_id=report.chunk.chunk_id,
            worker_name=report.worker_name,
            model=report.model,
            raw_run_id=report.raw_run_id,
        )
        alignment = self._aligner(
            candidates=report.candidates,
            chunk=report.chunk,
            schema=request.task.entity_schema,
            options=request.options,
            provenance_base=provenance,
        )
        state.unresolved_total += alignment.unresolved_count
        state.warnings.extend(report.warnings)
        state.warnings.extend(alignment.warnings)

        doc_id = report.chunk.document_id
        merged, additions = self._merger(
            state.document_extractions[doc_id],
            alignment.aligned,
        )
        state.document_extractions[doc_id] = merged
        return additions

    def _validate_reports(
        self,
        *,
        run_id: str,
        pass_id: int,
        chunks: list[TextChunk],
        reports: list[ChunkExtractionReport],
    ) -> None:
        expected = {chunk.chunk_id: chunk for chunk in chunks}
        actual_ids = [report.chunk.chunk_id for report in reports]
        if len(actual_ids) != len(set(actual_ids)):
            raise RuntimeIntegrationError(f"Runtime returned duplicate reports for pass {pass_id}")
        if set(actual_ids) != set(expected):
            missing = sorted(set(expected) - set(actual_ids))
            unexpected = sorted(set(actual_ids) - set(expected))
            raise RuntimeIntegrationError(
                f"Runtime report mismatch for pass {pass_id}: "
                f"missing={missing}, unexpected={unexpected}"
            )
        for report in reports:
            if report.run_id != run_id or report.pass_id != pass_id:
                raise RuntimeIntegrationError(
                    f"Runtime report metadata does not match pass {pass_id}"
                )
            if report.chunk != expected[report.chunk.chunk_id]:
                raise RuntimeIntegrationError(
                    f"Runtime changed chunk '{report.chunk.chunk_id}' in pass {pass_id}"
                )

    def _finalize(
        self,
        state: EngineRunState,
        request: ExtractRequest,
    ) -> ExtractResult:
        documents_result: list[DocumentResult] = []
        for document in state.documents:
            extractions = state.document_extractions.get(document.document_id, [])
            canonical_claims = []
            if request.runtime.reconciliation.enabled:
                if state.reconciliation_runtime is None:
                    if state.async_reconciliation_runtime is not None:
                        message = "Runtime only supports async reconciliation; use aextract()"
                    else:
                        message = "Runtime does not support requested document reconciliation"
                    raise RuntimeIntegrationError(message)
                reconciliation = state.reconciliation_runtime.reconcile_document(
                    run_id=state.run_id,
                    document=document,
                    extractions=extractions,
                    task_instructions=request.task.instructions,
                )
                extractions = reconciliation.reconciled_extractions
                canonical_claims = reconciliation.canonical_claims
                state.warnings.extend(reconciliation.warnings)
                state.trace_collector.add_events(reconciliation.events)
            documents_result.append(
                DocumentResult(
                    document_id=document.document_id,
                    text=document.text,
                    extractions=extractions,
                    canonical_claims=canonical_claims,
                )
            )
        return self._build_result(state, documents_result)

    async def _finalize_async(
        self,
        state: EngineRunState,
        request: ExtractRequest,
    ) -> ExtractResult:
        documents_result: list[DocumentResult] = []
        for document in state.documents:
            extractions = state.document_extractions.get(document.document_id, [])
            canonical_claims = []
            if request.runtime.reconciliation.enabled:
                if state.async_reconciliation_runtime is not None:
                    reconciliation = await state.async_reconciliation_runtime.areconcile_document(
                        run_id=state.run_id,
                        document=document,
                        extractions=extractions,
                        task_instructions=request.task.instructions,
                    )
                elif state.reconciliation_runtime is not None:
                    reconciliation = state.reconciliation_runtime.reconcile_document(
                        run_id=state.run_id,
                        document=document,
                        extractions=extractions,
                        task_instructions=request.task.instructions,
                    )
                else:
                    raise RuntimeIntegrationError(
                        "Runtime does not support requested document reconciliation"
                    )
                extractions = reconciliation.reconciled_extractions
                canonical_claims = reconciliation.canonical_claims
                state.warnings.extend(reconciliation.warnings)
                state.trace_collector.add_events(reconciliation.events)
            documents_result.append(
                DocumentResult(
                    document_id=document.document_id,
                    text=document.text,
                    extractions=extractions,
                    canonical_claims=canonical_claims,
                )
            )
        return self._build_result(state, documents_result)

    def _build_result(
        self,
        state: EngineRunState,
        documents: list[DocumentResult],
    ) -> ExtractResult:
        state.metrics.candidates_total = state.total_candidates
        state.metrics.extracted_total = sum(len(document.extractions) for document in documents)
        state.metrics.unresolved_total = state.unresolved_total
        state.metrics.passes_executed = state.pass_count
        state.metrics.finished_at = utc_now()
        run_trace = state.trace_collector.finalize(
            chunk_ids=state.chunk_ids,
            pass_ids=list(range(1, state.pass_count + 1)),
        )
        return ExtractResult(
            documents=documents,
            run_trace=run_trace,
            metrics=state.metrics,
            warnings=state.warnings,
        )


def extract(request: ExtractRequest, engine: SourceryEngine | None = None) -> ExtractResult:
    selected_engine = engine or SourceryEngine()
    return selected_engine.extract(request)


async def aextract(request: ExtractRequest, engine: SourceryEngine | None = None) -> ExtractResult:
    selected_engine = engine or SourceryEngine()
    return await selected_engine.aextract(request)
