from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import ValidationError

from sourcery.contracts import TextChunk
from sourcery.exceptions import (
    ErrorContext,
    RuntimeIntegrationError,
    SourceryRetryExhaustedError,
    SourceryRuntimeError,
)
from sourcery.runtime.blackgeorge_models import SessionRefinementPayload, SessionRefinementResult
from sourcery.runtime.blackgeorge_protocols import BlackGeorgeRefinementRuntime
from sourcery.runtime.errors import classify_provider_errors


class BlackGeorgeRefinementMixin:
    _REFINEMENT_WORKER_NAME = "RefinementWorker"

    def _build_refinement_contexts(
        self: BlackGeorgeRefinementRuntime,
        *,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
    ) -> dict[str, str]:
        config = self._runtime_config.session_refinement
        if not config.enabled:
            return {}

        worker = self._blackgeorge.Worker(
            name=f"{self._REFINEMENT_WORKER_NAME}:{pass_id}",
            instructions=(
                "You maintain cross-chunk extraction continuity. Return only a concise refinement context "
                "that helps the next chunk resolve entity references and naming consistency."
            ),
        )
        contexts: dict[str, str] = {}
        for document_id, ordered_chunks in self._group_chunks_for_refinement(chunks):
            session_id = f"sourcery-refinement:{run_id}:p{pass_id}:{document_id}"
            session = self._desk.session(
                worker,
                session_id=session_id,
                metadata={"run_id": run_id, "pass_id": pass_id, "document_id": document_id},
            )
            if session is None:
                continue

            for chunk in ordered_chunks:
                refined = ""
                for turn in range(1, config.max_turns + 1):
                    payload = SessionRefinementPayload(
                        chunk_id=chunk.chunk_id,
                        document_id=chunk.document_id,
                        pass_id=pass_id,
                        chunk_text=chunk.text,
                        previous_context=chunk.previous_context if turn == 1 else refined,
                    ).model_dump(mode="json")
                    payload["task_instructions"] = task_instructions
                    payload["turn"] = turn
                    context = ErrorContext(
                        run_id=run_id,
                        pass_id=pass_id,
                        chunk_id=chunk.chunk_id,
                        model=self._runtime_config.model,
                        provider=self._provider_name(),
                    )
                    try:
                        report = self._run_session_with_retries(
                            session=session,
                            payload=payload,
                            context=context,
                        )
                        data = report.data
                        if data is None:
                            break
                        parsed = SessionRefinementResult.model_validate(data)
                        candidate = parsed.refinement_context.strip()
                        if not candidate:
                            break
                        refined = candidate
                    except SourceryRuntimeError:
                        refined = ""
                        break
                    except ValidationError as exc:
                        raise RuntimeIntegrationError(
                            "Refinement response validation failed",
                            context=context,
                        ) from exc
                if refined:
                    contexts[chunk.chunk_id] = refined[: config.context_chars]
        return contexts

    def _group_chunks_for_refinement(
        self: BlackGeorgeRefinementRuntime,
        chunks: Sequence[TextChunk],
    ) -> list[tuple[str, list[TextChunk]]]:
        grouped: dict[str, list[TextChunk]] = {}
        for chunk in chunks:
            grouped.setdefault(chunk.document_id, []).append(chunk)
        for document_chunks in grouped.values():
            document_chunks.sort(key=lambda chunk: chunk.order_index)
        return list(grouped.items())

    def _run_session_with_retries(
        self: BlackGeorgeRefinementRuntime,
        *,
        session: Any,
        payload: dict[str, Any],
        context: ErrorContext,
    ) -> Any:
        attempts = 0
        last_error: Exception | None = None

        while attempts < self._retry.max_attempts:
            attempts += 1
            try:
                report = session.run(payload, response_schema=SessionRefinementResult, stream=False)
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
                errors = [
                    f"Refinement run returned status '{report.status}' without explicit errors"
                ]
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
            "Refinement retries exhausted without a completed report",
            attempts=attempts,
            context=context,
        )
