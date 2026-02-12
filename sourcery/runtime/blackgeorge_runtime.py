from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

from sourcery.contracts import (
    AlignedExtraction,
    ChunkExtractionReport,
    DocumentReconciliationReport,
    EventRecord,
    RetryPolicy,
    RuntimeConfig,
    SourceDocument,
    TextChunk,
)
from sourcery.exceptions import SourceryRuntimeError
from sourcery.pipeline.prompt_compiler import PromptCompiler
from sourcery.runtime.base import ChunkRuntime, DocumentReconciliationRuntime
from sourcery.runtime.blackgeorge_flow_mixin import BlackGeorgeFlowMixin
from sourcery.runtime.blackgeorge_models import event_to_record
from sourcery.runtime.blackgeorge_reconciliation_mixin import BlackGeorgeReconciliationMixin
from sourcery.runtime.blackgeorge_refinement_mixin import BlackGeorgeRefinementMixin
from sourcery.runtime.blackgeorge_retry_mixin import BlackGeorgeRetryMixin
from sourcery.runtime.model_gateway import build_chunk_candidate_schema


class BlackGeorgeNotInstalledError(RuntimeError):
    pass


class BlackGeorgeRuntime(
    BlackGeorgeRetryMixin,
    BlackGeorgeRefinementMixin,
    BlackGeorgeReconciliationMixin,
    BlackGeorgeFlowMixin,
    ChunkRuntime,
    DocumentReconciliationRuntime,
):
    _REFINEMENT_WORKER_NAME = "RefinementWorker"
    _COREFERENCE_WORKER_NAME = "CoreferenceWorker"
    _RESOLVER_WORKER_NAME = "DocumentResolverWorker"
    _runtime_config: RuntimeConfig
    _schema_set: Any
    _prompt_compiler: PromptCompiler
    _retry: RetryPolicy
    _blackgeorge: Any
    _Parallel: Any
    _Step: Any
    _desk: Any
    _events: list[EventRecord]
    _response_schema: Any

    def __init__(
        self,
        runtime_config: RuntimeConfig,
        schema_set: Any,
        prompt_compiler: PromptCompiler,
    ) -> None:
        self._runtime_config = runtime_config
        self._schema_set = schema_set
        self._prompt_compiler = prompt_compiler
        self._retry = runtime_config.retry

        try:
            import blackgeorge
            from blackgeorge.workflow import Parallel, Step

            self._blackgeorge = blackgeorge
            self._Parallel = Parallel
            self._Step = Step
        except ImportError as exc:
            raise BlackGeorgeNotInstalledError(
                "blackgeorge package is required for BlackGeorgeRuntime"
            ) from exc

        self._desk = self._blackgeorge.Desk(
            model=self._runtime_config.model,
            temperature=self._runtime_config.temperature,
            max_tokens=self._runtime_config.max_tokens,
            stream=self._runtime_config.stream,
            respect_context_window=self._runtime_config.respect_context_window,
            storage_dir=self._runtime_config.storage_dir,
        )
        self._events: list[EventRecord] = []
        self._register_event_handlers()
        self._response_schema = build_chunk_candidate_schema(self._schema_set)

    def _register_event_handlers(self) -> None:
        event_types = [
            "run.started",
            "run.completed",
            "run.failed",
            "run.paused",
            "run.resumed",
            "worker.started",
            "worker.completed",
            "worker.failed",
            "worker.paused",
            "step.started",
            "step.completed",
            "step.failed",
            "step.paused",
            "llm.started",
            "llm.completed",
            "llm.failed",
            "tool.started",
            "tool.completed",
            "tool.failed",
        ]

        def handle(event: Any) -> None:
            self._events.append(event_to_record(event))

        for event_type in event_types:
            self._desk.event_bus.subscribe(event_type, handle)

    @property
    def events(self) -> list[EventRecord]:
        return list(self._events)

    def run_pass(
        self,
        *,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
        batch_concurrency: int,
    ) -> list[ChunkExtractionReport]:
        if not chunks:
            return []

        refinement_contexts = self._build_refinement_contexts(
            run_id=run_id,
            pass_id=pass_id,
            chunks=chunks,
            task_instructions=task_instructions,
        )
        reports: list[ChunkExtractionReport] = []
        for batch in self._chunk_batches(chunks, max(batch_concurrency, 1)):
            reports.extend(
                self._run_flow_batch(
                    run_id=run_id,
                    pass_id=pass_id,
                    chunks=batch,
                    task_instructions=task_instructions,
                    refinement_contexts=refinement_contexts,
                )
            )
        input_order = {chunk.chunk_id: index for index, chunk in enumerate(chunks)}
        reports.sort(key=lambda report: input_order.get(report.chunk.chunk_id, len(input_order)))
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
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.run_pass(
                run_id=run_id,
                pass_id=pass_id,
                chunks=chunks,
                task_instructions=task_instructions,
                batch_concurrency=batch_concurrency,
            ),
        )

    def replay_run(self, raw_run_id: str) -> tuple[dict[str, Any] | None, list[EventRecord]]:
        record = self._desk.run_store.get_run(raw_run_id)
        if record is None:
            return None, []

        events = [event_to_record(event) for event in self._desk.run_store.get_events(raw_run_id)]
        payload: dict[str, Any] = {
            "run_id": record.run_id,
            "status": record.status,
            "input": record.input,
            "output": record.output,
            "output_json": record.output_json,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "state": record.state.model_dump(mode="json") if record.state is not None else None,
        }
        return payload, events

    def reconcile_document(
        self,
        *,
        run_id: str,
        document: SourceDocument,
        extractions: Sequence[AlignedExtraction],
        task_instructions: str,
    ) -> DocumentReconciliationReport:
        resolved_extractions = list(extractions)
        if not resolved_extractions:
            return DocumentReconciliationReport(
                document_id=document.document_id,
                reconciled_extractions=[],
            )

        if not self._runtime_config.reconciliation.enabled:
            return DocumentReconciliationReport(
                document_id=document.document_id,
                reconciled_extractions=resolved_extractions,
            )

        fallback_claims = self._fallback_canonical_claims(
            document_id=document.document_id,
            extractions=resolved_extractions,
        )
        if not self._runtime_config.reconciliation.use_workforce:
            return DocumentReconciliationReport(
                document_id=document.document_id,
                reconciled_extractions=resolved_extractions,
                canonical_claims=fallback_claims,
            )

        try:
            reconciliation_report = self._run_reconciliation_workforce(
                run_id=run_id,
                document=document,
                extractions=resolved_extractions,
                task_instructions=task_instructions,
            )
            if not reconciliation_report.canonical_claims:
                reconciliation_report.canonical_claims = fallback_claims
            return reconciliation_report
        except SourceryRuntimeError as exc:
            return DocumentReconciliationReport(
                document_id=document.document_id,
                reconciled_extractions=resolved_extractions,
                canonical_claims=fallback_claims,
                warnings=[f"Reconciliation fallback ({type(exc).__name__}): {exc}"],
            )
