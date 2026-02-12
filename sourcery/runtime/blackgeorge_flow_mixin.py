from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

from sourcery.contracts import ChunkExtractionReport, EventRecord, TextChunk
from sourcery.exceptions import ErrorContext, RuntimeIntegrationError, SourceryRetryExhaustedError
from sourcery.runtime.blackgeorge_models import event_to_record
from sourcery.runtime.blackgeorge_protocols import BlackGeorgeFlowRuntime
from sourcery.runtime.errors import classify_provider_errors
from sourcery.runtime.model_gateway import parse_candidates_from_structured_data


class BlackGeorgeFlowMixin:
    def _run_flow_batch(
        self: BlackGeorgeFlowRuntime,
        *,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
        refinement_contexts: dict[str, str],
    ) -> list[ChunkExtractionReport]:
        flow, flow_job, worker_names = self._build_flow_for_chunks(
            run_id=run_id,
            pass_id=pass_id,
            chunks=chunks,
            task_instructions=task_instructions,
            refinement_contexts=refinement_contexts,
        )
        flow_report = self._run_flow_with_retries(
            flow=flow,
            flow_job=flow_job,
            context=ErrorContext(
                run_id=run_id,
                pass_id=pass_id,
                model=self._runtime_config.model,
                provider=self._provider_name(),
            ),
        )
        return self._reports_from_flow_report(
            run_id=run_id,
            pass_id=pass_id,
            chunks=chunks,
            worker_names=worker_names,
            flow_report=flow_report,
        )

    def _provider_name(self: BlackGeorgeFlowRuntime) -> str:
        model_name = str(self._runtime_config.model)
        return model_name.split("/", 1)[0]

    def _chunk_batches(
        self: BlackGeorgeFlowRuntime,
        chunks: Sequence[TextChunk],
        batch_size: int,
    ) -> Iterator[list[TextChunk]]:
        for start in range(0, len(chunks), batch_size):
            yield list(chunks[start : start + batch_size])

    def _build_flow_for_chunks(
        self: BlackGeorgeFlowRuntime,
        *,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
        refinement_contexts: dict[str, str],
    ) -> tuple[Any, Any, dict[str, str]]:
        steps: list[Any] = []
        worker_names: dict[str, str] = {}

        for chunk in chunks:
            envelope = self._prompt_compiler.compile(
                self._schema_set,
                chunk,
                pass_id,
                instructions=task_instructions,
                refinement_context=refinement_contexts.get(chunk.chunk_id),
            )
            worker_name = f"ExtractorWorker:{pass_id}:{chunk.order_index}"
            worker = self._blackgeorge.Worker(
                name=worker_name,
                instructions=envelope.system,
            )
            job = self._blackgeorge.Job(
                input=envelope.user,
                response_schema=self._response_schema,
            )

            def job_builder(_context: Any, *, _job: Any = job) -> Any:
                return _job

            step = self._Step(
                worker,
                name=chunk.chunk_id,
                job_builder=job_builder,
            )
            steps.append(step)
            worker_names[chunk.chunk_id] = worker_name

        parallel = self._Parallel(*steps)
        flow = self._desk.flow([parallel], name=f"sourcery-flow:{run_id}:p{pass_id}")
        flow_job = self._blackgeorge.Job(
            input={
                "run_id": run_id,
                "pass_id": pass_id,
                "chunk_ids": [chunk.chunk_id for chunk in chunks],
            }
        )
        return flow, flow_job, worker_names

    def _run_flow_with_retries(
        self: BlackGeorgeFlowRuntime,
        *,
        flow: Any,
        flow_job: Any,
        context: ErrorContext,
    ) -> Any:
        attempts = 0
        last_error: Exception | None = None

        while attempts < self._retry.max_attempts:
            attempts += 1
            try:
                flow_report = flow.run(flow_job)
            except Exception as exc:
                last_error = exc
                if self._should_retry_exception(exc):
                    if attempts < self._retry.max_attempts:
                        self._sleep_before_retry(attempts)
                        continue
                    raise SourceryRetryExhaustedError(
                        str(exc),
                        attempts=attempts,
                        context=context,
                    ) from exc
                raise RuntimeIntegrationError(str(exc), context=context) from exc

            flow_report = self._resume_if_paused(flow=flow, report=flow_report, context=context)
            if flow_report.status == "completed":
                return flow_report

            errors = [error for error in getattr(flow_report, "errors", []) or []]
            if not errors:
                errors = [
                    f"Flow returned status '{flow_report.status}' without explicit error details"
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
                str(last_error),
                attempts=attempts,
                context=context,
            ) from last_error

        raise SourceryRetryExhaustedError(
            "Runtime retries exhausted without a completed report",
            attempts=attempts,
            context=context,
        )

    def _reports_from_flow_report(
        self: BlackGeorgeFlowRuntime,
        *,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        worker_names: dict[str, str],
        flow_report: Any,
    ) -> list[ChunkExtractionReport]:
        data_entries = self._resolve_data_entries(
            getattr(flow_report, "data", None), expected=len(chunks)
        )
        errors = [error for error in getattr(flow_report, "errors", []) or []]
        flow_events = [event for event in getattr(flow_report, "events", []) or []]

        worker_name_values = set(worker_names.values())
        chunk_name_values = set(worker_names.keys())
        shared_events = [
            event
            for event in flow_events
            if getattr(event, "source", "") not in worker_name_values
            and getattr(event, "source", "") not in chunk_name_values
        ]
        shared_records: list[EventRecord] = [event_to_record(event) for event in shared_events]

        reports: list[ChunkExtractionReport] = []
        for index, chunk in enumerate(chunks):
            data_obj = data_entries[index] if index < len(data_entries) else None
            candidates = parse_candidates_from_structured_data(data_obj)
            worker_name = worker_names.get(chunk.chunk_id, "ExtractorWorker")
            chunk_events = [
                event_to_record(event)
                for event in flow_events
                if self._event_matches_chunk(
                    event=event,
                    chunk=chunk,
                    worker_name=worker_name,
                )
            ]
            if index == 0:
                chunk_events = shared_records + chunk_events
            warnings = list(errors) if index == 0 else []
            reports.append(
                ChunkExtractionReport(
                    run_id=run_id,
                    pass_id=pass_id,
                    chunk=chunk,
                    candidates=candidates,
                    warnings=warnings,
                    events=chunk_events,
                    worker_name=worker_name,
                    model=self._runtime_config.model,
                    raw_run_id=getattr(flow_report, "run_id", None),
                )
            )
        return reports

    def _resolve_data_entries(
        self: BlackGeorgeFlowRuntime, data_obj: Any, *, expected: int
    ) -> list[Any]:
        if expected <= 0:
            return []
        if expected == 1:
            if isinstance(data_obj, list):
                if not data_obj:
                    return [None]
                first = data_obj[0]
                if isinstance(first, dict) and "data" in first:
                    return [first.get("data")]
                return [first]
            return [data_obj]
        if isinstance(data_obj, list):
            if len(data_obj) >= expected and all(
                isinstance(item, dict) and "data" in item for item in data_obj[:expected]
            ):
                return [item.get("data") for item in data_obj[:expected]]
            if len(data_obj) >= expected:
                return list(data_obj[:expected])
        return [None for _ in range(expected)]

    def _event_matches_chunk(
        self: BlackGeorgeFlowRuntime,
        *,
        event: Any,
        chunk: TextChunk,
        worker_name: str,
    ) -> bool:
        source = str(getattr(event, "source", ""))
        if source == chunk.chunk_id or source == worker_name:
            return True
        payload = dict(getattr(event, "payload", {}) or {})
        return payload.get("chunk_id") == chunk.chunk_id
