from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from sourcery.contracts import (
    AlignedExtraction,
    CanonicalClaim,
    ChunkExtractionReport,
    DocumentReconciliationReport,
    RetryPolicy,
    RuntimeConfig,
    SourceDocument,
    TextChunk,
)
from sourcery.exceptions import ErrorContext
from sourcery.pipeline.prompt_compiler import PromptCompiler
from sourcery.runtime.blackgeorge_models import ReconciliationWorkerOutput


class BlackGeorgeRetryRuntime(Protocol):
    _retry: RetryPolicy
    _desk: Any
    _runtime_config: RuntimeConfig

    def _should_retry_exception(self, exc: Exception) -> bool: ...
    def _sleep_before_retry(self, attempt: int) -> None: ...
    def _resume_report_with_desk(self, *, report: Any, context: ErrorContext) -> Any: ...
    def _resume_if_paused(self, *, flow: Any, report: Any, context: ErrorContext) -> Any: ...
    def _should_retry_errors(self, errors: Sequence[str]) -> bool: ...


class BlackGeorgeRefinementRuntime(BlackGeorgeRetryRuntime, Protocol):
    _blackgeorge: Any
    _REFINEMENT_WORKER_NAME: str

    def _provider_name(self) -> str: ...
    def _group_chunks_for_refinement(
        self, chunks: Sequence[TextChunk]
    ) -> list[tuple[str, list[TextChunk]]]: ...
    def _run_session_with_retries(
        self, *, session: Any, payload: dict[str, Any], context: ErrorContext
    ) -> Any: ...


class BlackGeorgeFlowRuntime(BlackGeorgeRetryRuntime, Protocol):
    _prompt_compiler: PromptCompiler
    _schema_set: Any
    _blackgeorge: Any
    _response_schema: Any
    _Step: Any
    _Parallel: Any

    def _provider_name(self) -> str: ...
    def _build_flow_for_chunks(
        self,
        *,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
        refinement_contexts: dict[str, str],
    ) -> tuple[Any, Any, dict[str, str]]: ...
    def _run_flow_with_retries(self, *, flow: Any, flow_job: Any, context: ErrorContext) -> Any: ...
    def _reports_from_flow_report(
        self,
        *,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        worker_names: dict[str, str],
        flow_report: Any,
    ) -> list[ChunkExtractionReport]: ...
    def _resolve_data_entries(self, data_obj: Any, *, expected: int) -> list[Any]: ...
    def _event_matches_chunk(self, *, event: Any, chunk: TextChunk, worker_name: str) -> bool: ...


class BlackGeorgeReconciliationRuntime(BlackGeorgeRetryRuntime, Protocol):
    _blackgeorge: Any
    _COREFERENCE_WORKER_NAME: str
    _RESOLVER_WORKER_NAME: str

    def _provider_name(self) -> str: ...
    def _serialize_extractions(
        self, extractions: Sequence[AlignedExtraction]
    ) -> list[dict[str, Any]]: ...
    def _run_workforce_with_retries(
        self, *, workforce: Any, job: Any, context: ErrorContext
    ) -> Any: ...
    def _resolve_worker_data(self, *, data_obj: Any, worker_name: str) -> Any | None: ...
    def _sanitize_indices(self, indices: Sequence[int], total: int) -> list[int]: ...
    def _canonical_claims_from_worker(
        self,
        *,
        document_id: str,
        extractions: Sequence[AlignedExtraction],
        resolver_output: ReconciliationWorkerOutput,
        allowed_indices: set[int],
    ) -> list[CanonicalClaim]: ...
    def _dump_attributes(self, attributes: Any) -> dict[str, Any]: ...
    def _mean_confidence(self, extractions: Sequence[AlignedExtraction]) -> float | None: ...
    def _fallback_canonical_claims(
        self,
        *,
        document_id: str,
        extractions: Sequence[AlignedExtraction],
    ) -> list[CanonicalClaim]: ...
    def _run_reconciliation_workforce(
        self,
        *,
        run_id: str,
        document: SourceDocument,
        extractions: list[AlignedExtraction],
        task_instructions: str,
    ) -> DocumentReconciliationReport: ...
