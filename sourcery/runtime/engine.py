from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Sequence
from typing import Callable

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
from sourcery.runtime.base import ChunkRuntime
from sourcery.runtime.base import DocumentReconciliationRuntime
from sourcery.runtime.blackgeorge_runtime import BlackGeorgeRuntime


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
        else:
            self._prompt_compiler = dependencies.prompt_compiler
            self._example_validator = dependencies.example_validator
            self._trace_collector_factory = dependencies.trace_collector_factory
            self._runtime_factory = dependencies.runtime_factory

    def extract(self, request: ExtractRequest) -> ExtractResult:
        return self._execute(request=request, runtime_async=False)

    async def aextract(self, request: ExtractRequest) -> ExtractResult:
        return await self._aexecute(request=request)

    def replay_run(
        self, request: ExtractRequest, raw_run_id: str
    ) -> tuple[dict[str, object] | None, list[EventRecord]]:
        runtime = self._make_runtime(request)
        replay, events = runtime.replay_run(raw_run_id)
        return replay, events

    def _make_runtime(self, request: ExtractRequest) -> ChunkRuntime:
        return self._runtime_factory(
            request.runtime,
            request.task.entity_schema,
            self._prompt_compiler,
        )

    def _normalize_documents(self, request: ExtractRequest) -> list[SourceDocument]:
        return request.normalize_documents()

    def _execute(self, *, request: ExtractRequest, runtime_async: bool) -> ExtractResult:
        run_id = new_run_id()
        started_at = utc_now()
        warnings: list[str] = []

        documents = self._normalize_documents(request)

        issues = self._example_validator.validate(
            task=request.task,
            fuzzy_threshold=request.options.fuzzy_alignment_threshold,
        )
        warnings.extend(self._example_validator.enforce_or_warn(task=request.task, issues=issues))

        metrics = RunMetrics(
            documents_total=len(documents),
            started_at=started_at,
        )
        trace_collector = self._trace_collector_factory(run_id=run_id, model=request.runtime.model)

        runtime = self._make_runtime(request)
        reconciliation_runtime: DocumentReconciliationRuntime | None = None
        if isinstance(runtime, DocumentReconciliationRuntime):
            reconciliation_runtime = runtime
        document_extractions: dict[str, list[AlignedExtraction]] = defaultdict(list)

        pass_count = 0
        total_candidates = 0
        unresolved_total = 0
        chunk_ids: list[str] = []

        for pass_id in range(1, request.options.max_passes + 1):
            pass_count = pass_id
            chunks = plan_chunks(
                documents,
                pass_id=pass_id,
                max_chunk_chars=request.options.max_chunk_chars,
                context_window_chars=request.options.context_window_chars,
            )
            chunk_ids.extend(chunk.chunk_id for chunk in chunks)
            metrics.chunks_total += len(chunks)

            reports = self._run_runtime_pass(
                runtime=runtime,
                run_id=run_id,
                pass_id=pass_id,
                chunks=chunks,
                task_instructions=request.task.instructions,
                runtime_async=runtime_async,
                batch_concurrency=request.options.batch_concurrency,
            )

            additions_this_pass = 0

            for report in reports:
                trace_collector.add_report_events(report)
                total_candidates += len(report.candidates)
                provenance = ExtractionProvenance(
                    run_id=run_id,
                    pass_id=pass_id,
                    chunk_id=report.chunk.chunk_id,
                    worker_name=report.worker_name,
                    model=report.model,
                    raw_run_id=report.raw_run_id,
                )
                alignment = align_candidates(
                    candidates=report.candidates,
                    chunk=report.chunk,
                    schema=request.task.entity_schema,
                    options=request.options,
                    provenance_base=provenance,
                )
                unresolved_total += alignment.unresolved_count
                warnings.extend(report.warnings)
                warnings.extend(alignment.warnings)

                merged, additions = merge_non_overlapping(
                    document_extractions[report.chunk.document_id],
                    alignment.aligned,
                )
                document_extractions[report.chunk.document_id] = merged
                additions_this_pass += additions

            if request.options.stop_when_no_new_extractions and additions_this_pass == 0:
                break

        metrics.candidates_total = total_candidates
        metrics.unresolved_total = unresolved_total
        metrics.passes_executed = pass_count
        metrics.finished_at = utc_now()

        documents_result: list[DocumentResult] = []
        for document in documents:
            extractions = document_extractions.get(document.document_id, [])
            canonical_claims = []
            if reconciliation_runtime is not None and request.runtime.reconciliation.enabled:
                reconciliation = reconciliation_runtime.reconcile_document(
                    run_id=run_id,
                    document=document,
                    extractions=extractions,
                    task_instructions=request.task.instructions,
                )
                extractions = reconciliation.reconciled_extractions
                canonical_claims = reconciliation.canonical_claims
                warnings.extend(reconciliation.warnings)
                trace_collector.add_events(reconciliation.events)
            documents_result.append(
                DocumentResult(
                    document_id=document.document_id,
                    text=document.text,
                    extractions=extractions,
                    canonical_claims=canonical_claims,
                )
            )

        metrics.extracted_total = sum(len(document.extractions) for document in documents_result)

        run_trace = trace_collector.finalize(
            chunk_ids=chunk_ids, pass_ids=list(range(1, pass_count + 1))
        )

        return ExtractResult(
            documents=documents_result,
            run_trace=run_trace,
            metrics=metrics,
            warnings=warnings,
        )

    def _run_runtime_pass(
        self,
        *,
        runtime: ChunkRuntime,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
        runtime_async: bool,
        batch_concurrency: int,
    ) -> list[ChunkExtractionReport]:
        if runtime_async:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is None:
                return asyncio.run(
                    runtime.arun_pass(
                        run_id=run_id,
                        pass_id=pass_id,
                        chunks=chunks,
                        task_instructions=task_instructions,
                        batch_concurrency=batch_concurrency,
                    )
                )

        return runtime.run_pass(
            run_id=run_id,
            pass_id=pass_id,
            chunks=chunks,
            task_instructions=task_instructions,
            batch_concurrency=batch_concurrency,
        )

    async def _aexecute(self, *, request: ExtractRequest) -> ExtractResult:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self._execute(request=request, runtime_async=True)
        )


def extract(request: ExtractRequest, engine: SourceryEngine | None = None) -> ExtractResult:
    selected_engine = engine or SourceryEngine()
    return selected_engine.extract(request)


async def aextract(request: ExtractRequest, engine: SourceryEngine | None = None) -> ExtractResult:
    selected_engine = engine or SourceryEngine()
    return await selected_engine.aextract(request)
