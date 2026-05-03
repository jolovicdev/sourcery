from __future__ import annotations

from collections import defaultdict
from collections.abc import Generator, Sequence
from dataclasses import dataclass, field
from typing import Any, Callable, Union

from sourcery.contracts import (
    AlignedExtraction,
    ChunkExtractionReport,
    DocumentResult,
    EngineDependencies,
    ExtractRequest,
    ExtractResult,
    ExtractionProvenance,
    RunMetrics,
    SourceDocument,
    StreamChunkDone,
    StreamExtractionAdded,
    StreamPassDone,
    TextChunk,
    EventRecord,
    new_run_id,
    utc_now,
)
from sourcery.observability.trace import RunTraceCollector
from sourcery.pipeline import (
    ExampleValidator,
    PromptCompiler,
    align_candidates,
    merge_non_overlapping,
    plan_chunks,
)
from sourcery.runtime.base import AsyncDocumentReconciliationRuntime, ChunkRuntime
from sourcery.runtime.base import DocumentReconciliationRuntime
from sourcery.runtime.blackgeorge_runtime import BlackGeorgeRuntime


def _extraction_key(ext: AlignedExtraction) -> tuple[Any, ...]:
    return (
        ext.entity,
        ext.text,
        ext.char_start,
        ext.char_end,
        ext.alignment_status,
        ext.provenance.pass_id,
        ext.provenance.chunk_id,
        id(ext),
    )


@dataclass
class EngineRunState:
    run_id: str
    documents: list[SourceDocument]
    runtime: ChunkRuntime
    reconciliation_runtime: DocumentReconciliationRuntime | None
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

    # -- public API ------------------------------------------------------------

    def extract(self, request: ExtractRequest) -> ExtractResult:
        return self._execute(request=request)

    async def aextract(self, request: ExtractRequest) -> ExtractResult:
        return await self._aexecute(request=request)

    StreamEvent = Union[StreamExtractionAdded, StreamChunkDone, StreamPassDone]

    def extract_stream(
        self, request: ExtractRequest
    ) -> Generator[StreamEvent, None, ExtractResult]:
        result = yield from self._execute_stream(request=request)
        return result

    def replay_run(
        self, request: ExtractRequest, raw_run_id: str
    ) -> tuple[dict[str, object] | None, list[EventRecord]]:
        runtime = self._make_runtime(request)
        replay, events = runtime.replay_run(raw_run_id)
        return replay, events

    # -- helpers ---------------------------------------------------------------

    def _make_runtime(self, request: ExtractRequest) -> ChunkRuntime:
        return self._runtime_factory(
            request.runtime,
            request.task.entity_schema,
            self._prompt_compiler,
        )

    def _normalize_documents(self, request: ExtractRequest) -> list[SourceDocument]:
        return request.normalize_documents()

    def _start_run(self, request: ExtractRequest) -> EngineRunState:
        run_id = new_run_id()
        documents = self._normalize_documents(request)

        issues = self._example_validator.validate(
            task=request.task,
            fuzzy_threshold=request.options.fuzzy_alignment_threshold,
        )
        warnings: list[str] = []
        warnings.extend(self._example_validator.enforce_or_warn(task=request.task, issues=issues))

        runtime = self._make_runtime(request)
        reconciliation_runtime: DocumentReconciliationRuntime | None = None
        if isinstance(runtime, DocumentReconciliationRuntime):
            reconciliation_runtime = runtime

        metrics = RunMetrics(
            documents_total=len(documents),
            started_at=utc_now(),
        )
        trace_collector = self._trace_collector_factory(run_id=run_id, model=request.runtime.model)

        return EngineRunState(
            run_id=run_id,
            documents=documents,
            runtime=runtime,
            reconciliation_runtime=reconciliation_runtime,
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
        pass_id: int,
    ) -> int:
        state.trace_collector.add_report_events(report)
        state.total_candidates += len(report.candidates)

        provenance = ExtractionProvenance(
            run_id=state.run_id,
            pass_id=pass_id,
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

    def _finalize(
        self,
        state: EngineRunState,
        request: ExtractRequest,
    ) -> ExtractResult:
        state.metrics.candidates_total = state.total_candidates
        state.metrics.unresolved_total = state.unresolved_total
        state.metrics.passes_executed = state.pass_count
        state.metrics.finished_at = utc_now()

        documents_result: list[DocumentResult] = []
        for document in state.documents:
            extractions = state.document_extractions.get(document.document_id, [])
            canonical_claims = []
            if state.reconciliation_runtime is not None and request.runtime.reconciliation.enabled:
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

        state.metrics.extracted_total = sum(
            len(document.extractions) for document in documents_result
        )

        run_trace = state.trace_collector.finalize(
            chunk_ids=state.chunk_ids,
            pass_ids=list(range(1, state.pass_count + 1)),
        )

        return ExtractResult(
            documents=documents_result,
            run_trace=run_trace,
            metrics=state.metrics,
            warnings=state.warnings,
        )

    async def _finalize_async(
        self,
        state: EngineRunState,
        request: ExtractRequest,
    ) -> ExtractResult:
        state.metrics.candidates_total = state.total_candidates
        state.metrics.unresolved_total = state.unresolved_total
        state.metrics.passes_executed = state.pass_count
        state.metrics.finished_at = utc_now()

        documents_result: list[DocumentResult] = []
        for document in state.documents:
            extractions = state.document_extractions.get(document.document_id, [])
            canonical_claims = []
            if state.reconciliation_runtime is not None and request.runtime.reconciliation.enabled:
                if isinstance(state.reconciliation_runtime, AsyncDocumentReconciliationRuntime):
                    reconciliation = await state.reconciliation_runtime.areconcile_document(
                        run_id=state.run_id,
                        document=document,
                        extractions=extractions,
                        task_instructions=request.task.instructions,
                    )
                else:
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

        state.metrics.extracted_total = sum(
            len(document.extractions) for document in documents_result
        )

        run_trace = state.trace_collector.finalize(
            chunk_ids=state.chunk_ids,
            pass_ids=list(range(1, state.pass_count + 1)),
        )

        return ExtractResult(
            documents=documents_result,
            run_trace=run_trace,
            metrics=state.metrics,
            warnings=state.warnings,
        )

    # -- runtime pass adapters --------------------------------------------------

    def _run_runtime_pass(
        self,
        *,
        runtime: ChunkRuntime,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
        batch_concurrency: int,
    ) -> list[ChunkExtractionReport]:
        return runtime.run_pass(
            run_id=run_id,
            pass_id=pass_id,
            chunks=chunks,
            task_instructions=task_instructions,
            batch_concurrency=batch_concurrency,
        )

    async def _arun_runtime_pass(
        self,
        *,
        runtime: ChunkRuntime,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
        batch_concurrency: int,
    ) -> list[ChunkExtractionReport]:
        return await runtime.arun_pass(
            run_id=run_id,
            pass_id=pass_id,
            chunks=chunks,
            task_instructions=task_instructions,
            batch_concurrency=batch_concurrency,
        )

    # -- execution methods (thin orchestration) ---------------------------------

    def _execute(self, *, request: ExtractRequest) -> ExtractResult:
        state = self._start_run(request)
        batch_concurrency = request.options.batch_concurrency

        for pass_id in range(1, request.options.max_passes + 1):
            chunks = self._plan_pass(state, request, pass_id)
            reports = self._run_runtime_pass(
                runtime=state.runtime,
                run_id=state.run_id,
                pass_id=pass_id,
                chunks=chunks,
                task_instructions=request.task.instructions,
                batch_concurrency=batch_concurrency,
            )
            additions_this_pass = 0
            for report in reports:
                additions_this_pass += self._process_report(state, report, request, pass_id)
            if request.options.stop_when_no_new_extractions and additions_this_pass == 0:
                break

        return self._finalize(state, request)

    async def _aexecute(self, *, request: ExtractRequest) -> ExtractResult:
        state = self._start_run(request)
        batch_concurrency = request.options.batch_concurrency

        for pass_id in range(1, request.options.max_passes + 1):
            chunks = self._plan_pass(state, request, pass_id)
            reports = await self._arun_runtime_pass(
                runtime=state.runtime,
                run_id=state.run_id,
                pass_id=pass_id,
                chunks=chunks,
                task_instructions=request.task.instructions,
                batch_concurrency=batch_concurrency,
            )
            additions_this_pass = 0
            for report in reports:
                additions_this_pass += self._process_report(state, report, request, pass_id)
            if request.options.stop_when_no_new_extractions and additions_this_pass == 0:
                break

        return await self._finalize_async(state, request)

    def _execute_stream(
        self, *, request: ExtractRequest
    ) -> Generator[SourceryEngine.StreamEvent, None, ExtractResult]:
        state = self._start_run(request)

        for pass_id in range(1, request.options.max_passes + 1):
            chunks = self._plan_pass(state, request, pass_id)
            additions_this_pass = 0

            for chunk in chunks:
                reports = self._run_runtime_pass(
                    runtime=state.runtime,
                    run_id=state.run_id,
                    pass_id=pass_id,
                    chunks=[chunk],
                    task_instructions=request.task.instructions,
                    batch_concurrency=1,
                )
                for report in reports:
                    doc_id = report.chunk.document_id
                    pre_merge_keys = {
                        _extraction_key(ext) for ext in state.document_extractions[doc_id]
                    }
                    additions = self._process_report(state, report, request, pass_id)
                    additions_this_pass += additions
                    for extraction in state.document_extractions[doc_id]:
                        if _extraction_key(extraction) not in pre_merge_keys:
                            yield StreamExtractionAdded(document_id=doc_id, extraction=extraction)
                    yield StreamChunkDone(
                        chunk_id=report.chunk.chunk_id,
                        document_id=doc_id,
                        pass_id=pass_id,
                        candidates_found=len(report.candidates),
                    )

            yield StreamPassDone(
                pass_id=pass_id,
                additions_this_pass=additions_this_pass,
                extractions_so_far=sum(
                    len(extractions) for extractions in state.document_extractions.values()
                ),
            )

            if request.options.stop_when_no_new_extractions and additions_this_pass == 0:
                break

        return self._finalize(state, request)


def extract(request: ExtractRequest, engine: SourceryEngine | None = None) -> ExtractResult:
    selected_engine = engine or SourceryEngine()
    return selected_engine.extract(request)


async def aextract(request: ExtractRequest, engine: SourceryEngine | None = None) -> ExtractResult:
    selected_engine = engine or SourceryEngine()
    return await selected_engine.aextract(request)
