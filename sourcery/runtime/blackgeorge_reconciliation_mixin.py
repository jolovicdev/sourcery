from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sourcery.contracts import (
    AlignedExtraction,
    CanonicalClaim,
    DocumentReconciliationReport,
    SourceDocument,
)
from sourcery.exceptions import ErrorContext, RuntimeIntegrationError, SourceryRetryExhaustedError
from sourcery.runtime.blackgeorge_models import ReconciliationWorkerOutput, event_to_record
from sourcery.runtime.blackgeorge_protocols import BlackGeorgeReconciliationRuntime
from sourcery.runtime.errors import classify_provider_errors


class BlackGeorgeReconciliationMixin:
    _COREFERENCE_WORKER_NAME = "CoreferenceWorker"
    _RESOLVER_WORKER_NAME = "DocumentResolverWorker"

    def _run_reconciliation_workforce(
        self: BlackGeorgeReconciliationRuntime,
        *,
        run_id: str,
        document: SourceDocument,
        extractions: list[AlignedExtraction],
        task_instructions: str,
    ) -> DocumentReconciliationReport:
        from blackgeorge.collaboration import (
            Blackboard,
            Channel,
            blackboard_read_tool,
            blackboard_write_tool,
        )

        blackboard = Blackboard()
        channel = Channel()
        coreference_worker = self._blackgeorge.Worker(
            name=self._COREFERENCE_WORKER_NAME,
            instructions=(
                "Cluster equivalent entity mentions across all chunks. "
                "Write an object to blackboard key 'coreference_clusters' using blackboard_write. "
                "Then return mode='coreference' with a compact summary."
            ),
            tools=[blackboard_write_tool(blackboard, author=self._COREFERENCE_WORKER_NAME)],
        )
        resolver_worker = self._blackgeorge.Worker(
            name=self._RESOLVER_WORKER_NAME,
            instructions=(
                "Read blackboard key 'coreference_clusters' and produce canonical resolved entities/claims. "
                "Return mode='resolver', keep_indices, and canonical_claims."
            ),
            tools=[blackboard_read_tool(blackboard)],
        )
        workforce = self._blackgeorge.Workforce(
            [coreference_worker, resolver_worker],
            mode="collaborate",
            name=f"sourcery-reconcile:{run_id}:{document.document_id}",
            channel=channel,
            blackboard=blackboard,
        )
        job = self._blackgeorge.Job(
            input={
                "document_id": document.document_id,
                "task_instructions": task_instructions,
                "reconciliation_config": self._runtime_config.reconciliation.model_dump(
                    mode="json"
                ),
                "extractions": self._serialize_extractions(extractions),
            },
            response_schema=ReconciliationWorkerOutput,
        )
        context = ErrorContext(
            run_id=run_id,
            model=self._runtime_config.model,
            provider=self._provider_name(),
        )
        report = self._run_workforce_with_retries(
            workforce=workforce,
            job=job,
            context=context,
        )
        warnings = [error for error in getattr(report, "errors", []) or []]
        events = [event_to_record(event) for event in getattr(report, "events", []) or []]
        resolver_data = self._resolve_worker_data(
            data_obj=getattr(report, "data", None),
            worker_name=self._RESOLVER_WORKER_NAME,
        )
        if resolver_data is None:
            return DocumentReconciliationReport(
                document_id=document.document_id,
                reconciled_extractions=extractions,
                warnings=warnings + ["Resolver worker output missing from reconciliation run"],
                events=events,
                raw_run_id=getattr(report, "run_id", None),
            )

        resolver_output = ReconciliationWorkerOutput.model_validate(resolver_data)
        keep_indices = self._sanitize_indices(resolver_output.keep_indices, len(extractions))
        if not keep_indices:
            keep_indices = list(range(len(extractions)))
        reconciled = [extractions[index] for index in keep_indices]
        canonical_claims = self._canonical_claims_from_worker(
            document_id=document.document_id,
            extractions=extractions,
            resolver_output=resolver_output,
            allowed_indices=set(keep_indices),
        )
        return DocumentReconciliationReport(
            document_id=document.document_id,
            reconciled_extractions=reconciled,
            canonical_claims=canonical_claims,
            warnings=warnings,
            events=events,
            raw_run_id=getattr(report, "run_id", None),
        )

    def _run_workforce_with_retries(
        self: BlackGeorgeReconciliationRuntime,
        *,
        workforce: Any,
        job: Any,
        context: ErrorContext,
    ) -> Any:
        attempts = 0
        last_error: Exception | None = None

        while attempts < self._retry.max_attempts:
            attempts += 1
            try:
                report = self._desk.run(workforce, job, stream=self._runtime_config.stream)
            except Exception as exc:
                last_error = exc
                if self._should_retry_exception(exc):
                    if attempts < self._retry.max_attempts:
                        self._sleep_before_retry(attempts)
                        continue
                    raise SourceryRetryExhaustedError(
                        str(exc), attempts=attempts, context=context
                    ) from exc
                raise RuntimeIntegrationError(str(exc), context=context) from exc

            report = self._resume_report_with_desk(report=report, context=context)
            if report.status == "completed":
                return report

            errors = [error for error in getattr(report, "errors", []) or []]
            if not errors:
                errors = [f"Workforce returned status '{report.status}' without explicit errors"]
            classified = classify_provider_errors(errors, context=context)
            if self._should_retry_errors(errors):
                if attempts < self._retry.max_attempts:
                    self._sleep_before_retry(attempts)
                    continue
                raise SourceryRetryExhaustedError(
                    "; ".join(errors),
                    attempts=attempts,
                    context=context,
                ) from classified
            raise classified

        if last_error is not None:
            raise SourceryRetryExhaustedError(
                str(last_error), attempts=attempts, context=context
            ) from last_error
        raise SourceryRetryExhaustedError(
            "Reconciliation retries exhausted without a completed report",
            attempts=attempts,
            context=context,
        )

    def _serialize_extractions(
        self: BlackGeorgeReconciliationRuntime,
        extractions: Sequence[AlignedExtraction],
    ) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for index, extraction in enumerate(extractions):
            serialized.append(
                {
                    "index": index,
                    "entity": extraction.entity,
                    "text": extraction.text,
                    "alignment_status": extraction.alignment_status,
                    "confidence": extraction.confidence,
                    "char_start": extraction.char_start,
                    "char_end": extraction.char_end,
                    "attributes": self._dump_attributes(extraction.attributes),
                }
            )
        return serialized

    def _dump_attributes(self: BlackGeorgeReconciliationRuntime, attributes: Any) -> dict[str, Any]:
        if hasattr(attributes, "model_dump"):
            dumped = attributes.model_dump(mode="json")
            if isinstance(dumped, dict):
                return dict(dumped)
        return dict(attributes)

    def _resolve_worker_data(
        self: BlackGeorgeReconciliationRuntime,
        *,
        data_obj: Any,
        worker_name: str,
    ) -> Any | None:
        if not isinstance(data_obj, list):
            return None
        for item in data_obj:
            if not isinstance(item, dict):
                continue
            if item.get("worker") == worker_name:
                return item.get("data")
        return None

    def _sanitize_indices(
        self: BlackGeorgeReconciliationRuntime,
        indices: Sequence[int],
        total: int,
    ) -> list[int]:
        seen: set[int] = set()
        ordered: list[int] = []
        for index in indices:
            if index < 0 or index >= total:
                continue
            if index in seen:
                continue
            seen.add(index)
            ordered.append(index)
        return ordered

    def _canonical_claims_from_worker(
        self: BlackGeorgeReconciliationRuntime,
        *,
        document_id: str,
        extractions: Sequence[AlignedExtraction],
        resolver_output: ReconciliationWorkerOutput,
        allowed_indices: set[int],
    ) -> list[CanonicalClaim]:
        claims: list[CanonicalClaim] = []
        min_mentions = self._runtime_config.reconciliation.min_mentions_for_claim
        max_claims = self._runtime_config.reconciliation.max_claims
        for claim_index, claim in enumerate(resolver_output.canonical_claims[:max_claims]):
            mention_indices = self._sanitize_indices(claim.mention_indices, len(extractions))
            mention_indices = [index for index in mention_indices if index in allowed_indices]
            if len(mention_indices) < min_mentions:
                continue
            mention_extractions = [extractions[index] for index in mention_indices]
            entity = claim.entity.strip() or mention_extractions[0].entity
            canonical_text = claim.canonical_text.strip() or mention_extractions[0].text
            confidence = claim.confidence
            if confidence is None:
                confidence = self._mean_confidence(mention_extractions)
            attributes = dict(claim.attributes)
            if not attributes:
                attributes = self._dump_attributes(mention_extractions[0].attributes)
            claims.append(
                CanonicalClaim(
                    claim_id=f"{document_id}:claim:{claim_index}",
                    entity=entity,
                    canonical_text=canonical_text,
                    mention_count=len(mention_indices),
                    extraction_indices=mention_indices,
                    confidence=confidence,
                    attributes=attributes,
                )
            )
        return claims

    def _fallback_canonical_claims(
        self: BlackGeorgeReconciliationRuntime,
        *,
        document_id: str,
        extractions: Sequence[AlignedExtraction],
    ) -> list[CanonicalClaim]:
        min_mentions = self._runtime_config.reconciliation.min_mentions_for_claim
        max_claims = self._runtime_config.reconciliation.max_claims
        grouped: dict[tuple[str, str], list[int]] = {}
        for index, extraction in enumerate(extractions):
            if extraction.alignment_status == "unresolved":
                continue
            key = (extraction.entity.strip().lower(), extraction.text.strip().lower())
            grouped.setdefault(key, []).append(index)

        claims: list[CanonicalClaim] = []
        sorted_groups = sorted(
            grouped.items(),
            key=lambda item: (item[0][0], item[0][1], item[1][0]),
        )
        for claim_index, (_, indices) in enumerate(sorted_groups):
            if claim_index >= max_claims:
                break
            if len(indices) < min_mentions:
                continue
            first = extractions[indices[0]]
            claim_extractions = [extractions[index] for index in indices]
            claims.append(
                CanonicalClaim(
                    claim_id=f"{document_id}:claim:{claim_index}",
                    entity=first.entity,
                    canonical_text=first.text,
                    mention_count=len(indices),
                    extraction_indices=indices,
                    confidence=self._mean_confidence(claim_extractions),
                    attributes=self._dump_attributes(first.attributes),
                )
            )
        return claims

    def _mean_confidence(
        self: BlackGeorgeReconciliationRuntime,
        extractions: Sequence[AlignedExtraction],
    ) -> float | None:
        confidences = [
            value
            for value in (extraction.confidence for extraction in extractions)
            if value is not None
        ]
        if not confidences:
            return None
        return sum(confidences) / len(confidences)
