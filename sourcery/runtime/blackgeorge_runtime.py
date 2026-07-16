from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from pydantic import BaseModel, ValidationError

from sourcery.contracts import (
    AlignedExtraction,
    CanonicalClaim,
    ChunkExtractionReport,
    DocumentReconciliationReport,
    EventRecord,
    ReconciliationConfig,
    RetryPolicy,
    RuntimeConfig,
    SourceDocument,
    TextChunk,
)
from sourcery.exceptions import (
    ErrorContext,
    RuntimeIntegrationError,
    SourceryPausedRunError,
    SourceryRetryExhaustedError,
    SourceryRuntimeError,
)
from sourcery.pipeline.prompt_compiler import PromptCompiler
from sourcery.runtime.blackgeorge_models import (
    ReconciliationWorkerOutput,
    SessionRefinementResult,
    event_to_record,
)
from sourcery.runtime.errors import (
    classify_provider_errors,
    is_rate_limit_message,
    is_transient_message,
)
from sourcery.runtime.model_gateway import (
    build_chunk_candidate_schema,
    parse_candidates_from_structured_data,
)

REFINEMENT_WORKER = "RefinementWorker"
COREFERENCE_WORKER = "CoreferenceWorker"
RESOLVER_WORKER = "DocumentResolverWorker"


class BlackGeorgeNotInstalledError(RuntimeError):
    pass


def _retryable(policy: RetryPolicy, errors: Sequence[str]) -> bool:
    return (
        policy.retry_on_rate_limit and any(is_rate_limit_message(error) for error in errors)
    ) or (policy.retry_on_transient_errors and any(is_transient_message(error) for error in errors))


def _retry_delay(policy: RetryPolicy, attempt: int) -> float:
    return min(
        policy.initial_backoff_seconds * policy.backoff_multiplier ** (attempt - 1),
        policy.max_backoff_seconds,
    )


async def _arun_with_retries(
    policy: RetryPolicy,
    run: Callable[[], Awaitable[Any]],
    resume: Callable[..., Awaitable[Any]],
    context: ErrorContext,
    operation: str,
) -> Any:
    for attempt in range(1, policy.max_attempts + 1):
        try:
            report = await run()
        except Exception as exc:
            if not _retryable(policy, [str(exc)]):
                raise RuntimeIntegrationError(str(exc), context=context) from exc
            if attempt == policy.max_attempts:
                raise SourceryRetryExhaustedError(
                    str(exc), attempts=attempt, context=context
                ) from exc
            if delay := _retry_delay(policy, attempt):
                await asyncio.sleep(delay)
            continue

        if report.status == "paused":
            if not policy.auto_resume_paused_runs:
                raise SourceryPausedRunError(
                    "Run paused and auto-resume is disabled", context=context
                )
            for _ in range(policy.max_pause_resumes):
                if report.status != "paused":
                    break
                pending_action = getattr(report, "pending_action", None)
                if pending_action is None:
                    raise SourceryPausedRunError(
                        "Run paused without pending action", context=context
                    )
                decision: Any = (
                    True if getattr(pending_action, "type", "") == "confirmation" else ""
                )
                try:
                    report = await resume(report, decision)
                except Exception as exc:
                    raise RuntimeIntegrationError(str(exc), context=context) from exc
            if report.status == "paused":
                raise SourceryPausedRunError(
                    "Run stayed paused after max resume attempts", context=context
                )

        if report.status == "completed":
            return report

        errors = [str(error) for error in getattr(report, "errors", []) or []]
        if not errors:
            errors = [f"{operation} returned status '{report.status}' without explicit errors"]
        classified = classify_provider_errors(errors, context=context)
        if not _retryable(policy, errors):
            raise classified
        if attempt == policy.max_attempts:
            raise SourceryRetryExhaustedError(
                "; ".join(errors), attempts=attempt, context=context
            ) from classified
        if delay := _retry_delay(policy, attempt):
            await asyncio.sleep(delay)

    raise AssertionError("retry policy must allow at least one attempt")


def _flow_data(data: Any, expected: int) -> list[Any]:
    if data is None:
        raise RuntimeIntegrationError("BlackGeorge flow completed without structured data")
    if expected == 1:
        if not isinstance(data, list):
            return [data]
        if len(data) != 1:
            raise RuntimeIntegrationError(f"BlackGeorge returned {len(data)} outputs for one chunk")
        item = data[0]
        if isinstance(item, dict) and "data" in item:
            item = item["data"]
        if item is None:
            raise RuntimeIntegrationError(
                "BlackGeorge flow completed without structured chunk data"
            )
        return [item]
    if isinstance(data, list) and len(data) == expected:
        items = [item.get("data") for item in data if isinstance(item, dict) and "data" in item]
        if len(items) == expected and all(item is not None for item in items):
            return items
    raise RuntimeIntegrationError(
        f"BlackGeorge flow output does not contain {expected} chunk results"
    )


def _attributes(value: Any) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return dict(value)


def _valid_indices(indices: Sequence[int], total: int) -> list[int]:
    seen: set[int] = set()
    valid: list[int] = []
    for index in indices:
        if 0 <= index < total and index not in seen:
            seen.add(index)
            valid.append(index)
    return valid


def _mean_confidence(extractions: Sequence[AlignedExtraction]) -> float | None:
    values = [item.confidence for item in extractions if item.confidence is not None]
    return sum(values) / len(values) if values else None


def _fallback_claims(
    config: ReconciliationConfig,
    document_id: str,
    extractions: Sequence[AlignedExtraction],
) -> list[CanonicalClaim]:
    grouped: dict[tuple[str, str], list[int]] = {}
    for index, extraction in enumerate(extractions):
        if extraction.alignment_status != "unresolved":
            key = (extraction.entity.strip().casefold(), extraction.text.strip().casefold())
            grouped.setdefault(key, []).append(index)

    claims: list[CanonicalClaim] = []
    for _, indices in sorted(grouped.items(), key=lambda item: (*item[0], item[1][0])):
        if len(indices) < config.min_mentions_for_claim:
            continue
        first = extractions[indices[0]]
        mentions = [extractions[index] for index in indices]
        claims.append(
            CanonicalClaim(
                claim_id=f"{document_id}:claim:{len(claims)}",
                entity=first.entity,
                canonical_text=first.text,
                mention_count=len(indices),
                extraction_indices=indices,
                confidence=_mean_confidence(mentions),
                attributes=_attributes(first.attributes),
            )
        )
        if len(claims) == config.max_claims:
            break
    return claims


def _worker_claims(
    config: ReconciliationConfig,
    document_id: str,
    extractions: Sequence[AlignedExtraction],
    output: ReconciliationWorkerOutput,
    allowed_indices: set[int],
) -> list[CanonicalClaim]:
    claims: list[CanonicalClaim] = []
    for claim in output.canonical_claims:
        indices = [
            index
            for index in _valid_indices(claim.mention_indices, len(extractions))
            if index in allowed_indices
        ]
        if len(indices) < config.min_mentions_for_claim:
            continue
        mentions = [extractions[index] for index in indices]
        claims.append(
            CanonicalClaim(
                claim_id=f"{document_id}:claim:{len(claims)}",
                entity=claim.entity.strip() or mentions[0].entity,
                canonical_text=claim.canonical_text.strip() or mentions[0].text,
                mention_count=len(indices),
                extraction_indices=indices,
                confidence=(
                    claim.confidence if claim.confidence is not None else _mean_confidence(mentions)
                ),
                attributes=dict(claim.attributes) or _attributes(mentions[0].attributes),
            )
        )
        if len(claims) == config.max_claims:
            break
    return claims


class BlackGeorgeRuntime:
    def __init__(
        self,
        runtime_config: RuntimeConfig,
        schema_set: Any,
        prompt_compiler: PromptCompiler,
    ) -> None:
        try:
            import blackgeorge
            from blackgeorge.workflow import Parallel, Step
        except ModuleNotFoundError as exc:
            if exc.name != "blackgeorge":
                raise
            raise BlackGeorgeNotInstalledError(
                "blackgeorge package is required for BlackGeorgeRuntime"
            ) from exc

        self._runtime_config = runtime_config
        self._schema_set = schema_set
        self._prompt_compiler = prompt_compiler
        self._blackgeorge = blackgeorge
        self._Parallel = Parallel
        self._Step = Step
        self._desk = blackgeorge.Desk(
            model=runtime_config.model,
            temperature=runtime_config.temperature,
            max_tokens=runtime_config.max_tokens,
            stream=runtime_config.stream,
            respect_context_window=runtime_config.respect_context_window,
            storage_dir=runtime_config.storage_dir,
        )
        self._events: list[EventRecord] = []

        def record(event: Any) -> None:
            self._events.append(event_to_record(event))

        self._desk.event_bus.subscribe("*", record)
        self._response_schema = build_chunk_candidate_schema(schema_set)

    @property
    def events(self) -> list[EventRecord]:
        return list(self._events)

    def close(self) -> None:
        self._desk.close()

    def run_pass(
        self,
        *,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
        batch_concurrency: int,
    ) -> list[ChunkExtractionReport]:
        from blackgeorge.async_utils import ensure_not_running_loop

        ensure_not_running_loop("run_pass", "arun_pass")
        return asyncio.run(
            self.arun_pass(
                run_id=run_id,
                pass_id=pass_id,
                chunks=chunks,
                task_instructions=task_instructions,
                batch_concurrency=batch_concurrency,
            )
        )

    async def arun_pass(
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

        event_start = len(self._events)
        contexts = await self._arefinement_contexts(run_id, pass_id, chunks, task_instructions)
        reports: list[ChunkExtractionReport] = []
        batch_size = max(batch_concurrency, 1)
        for start in range(0, len(chunks), batch_size):
            batch = list(chunks[start : start + batch_size])
            flow, job, workers = self._flow(run_id, pass_id, batch, task_instructions, contexts)
            context = ErrorContext(
                run_id=run_id,
                pass_id=pass_id,
                model=self._runtime_config.model,
                provider=self._runtime_config.model.partition("/")[0],
            )
            report = await _arun_with_retries(
                self._runtime_config.retry,
                lambda: flow.arun(job),
                flow.aresume,
                context,
                "Chunk flow",
            )
            reports.extend(self._flow_reports(run_id, pass_id, batch, workers, report))

        order = {chunk.chunk_id: index for index, chunk in enumerate(chunks)}
        reports.sort(key=lambda report: order.get(report.chunk.chunk_id, len(order)))
        if reports:
            reported_event_ids = {event.event_id for report in reports for event in report.events}
            missing_events = [
                event
                for event in self._events[event_start:]
                if event.event_id not in reported_event_ids
            ]
            reports[0].events = missing_events + reports[0].events
        return reports

    def replay_run(self, raw_run_id: str) -> tuple[dict[str, Any] | None, list[EventRecord]]:
        record = self._desk.run_store.get_run(raw_run_id)
        if record is None:
            return None, []
        events = [event_to_record(event) for event in self._desk.run_store.get_events(raw_run_id)]
        return {
            "run_id": record.run_id,
            "status": record.status,
            "input": record.input,
            "output": record.output,
            "output_json": record.output_json,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
            "state": record.state.model_dump(mode="json") if record.state is not None else None,
        }, events

    def reconcile_document(
        self,
        *,
        run_id: str,
        document: SourceDocument,
        extractions: Sequence[AlignedExtraction],
        task_instructions: str,
    ) -> DocumentReconciliationReport:
        from blackgeorge.async_utils import ensure_not_running_loop

        ensure_not_running_loop("reconcile_document", "areconcile_document")
        return asyncio.run(
            self.areconcile_document(
                run_id=run_id,
                document=document,
                extractions=extractions,
                task_instructions=task_instructions,
            )
        )

    async def areconcile_document(
        self,
        *,
        run_id: str,
        document: SourceDocument,
        extractions: Sequence[AlignedExtraction],
        task_instructions: str,
    ) -> DocumentReconciliationReport:
        items = list(extractions)
        if not items or not self._runtime_config.reconciliation.enabled:
            return DocumentReconciliationReport(
                document_id=document.document_id,
                reconciled_extractions=items,
            )

        fallback = _fallback_claims(
            self._runtime_config.reconciliation, document.document_id, items
        )
        if not self._runtime_config.reconciliation.use_workforce:
            return DocumentReconciliationReport(
                document_id=document.document_id,
                reconciled_extractions=items,
                canonical_claims=fallback,
            )

        try:
            workforce, job, context = self._reconciliation_workforce(
                run_id, document, items, task_instructions
            )
            report = await _arun_with_retries(
                self._runtime_config.retry,
                lambda: self._desk.arun(workforce, job, stream=self._runtime_config.stream),
                self._desk.aresume,
                context,
                "Reconciliation workforce",
            )
            result = self._reconciliation_report(document, items, report, context)
            if not result.canonical_claims:
                result.canonical_claims = fallback
            return result
        except SourceryRuntimeError as exc:
            return DocumentReconciliationReport(
                document_id=document.document_id,
                reconciled_extractions=items,
                canonical_claims=fallback,
                warnings=[f"Reconciliation fallback ({type(exc).__name__}): {exc}"],
            )

    async def _arefinement_contexts(
        self,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
    ) -> dict[str, str]:
        config = self._runtime_config.session_refinement
        if not config.enabled:
            return {}

        grouped: dict[str, list[TextChunk]] = {}
        for chunk in chunks:
            grouped.setdefault(chunk.document_id, []).append(chunk)
        worker = self._blackgeorge.Worker(
            name=f"{REFINEMENT_WORKER}:{pass_id}",
            instructions=(
                "Maintain cross-chunk extraction continuity. Return only a concise refinement "
                "context that helps the next chunk resolve references and naming consistency."
            ),
        )
        contexts: dict[str, str] = {}
        for document_id, document_chunks in grouped.items():
            document_chunks.sort(key=lambda chunk: chunk.order_index)
            session = self._desk.session(
                worker,
                session_id=f"sourcery-refinement:{run_id}:p{pass_id}:{document_id}",
                metadata={"run_id": run_id, "pass_id": pass_id, "document_id": document_id},
            )
            if session is None:
                raise RuntimeIntegrationError(
                    f"Refinement session belongs to a different worker for document '{document_id}'"
                )
            try:
                for chunk in document_chunks:
                    refined = ""
                    context = ErrorContext(
                        run_id=run_id,
                        pass_id=pass_id,
                        chunk_id=chunk.chunk_id,
                        model=self._runtime_config.model,
                        provider=self._runtime_config.model.partition("/")[0],
                    )
                    for turn in range(1, config.max_turns + 1):
                        payload = {
                            "chunk_id": chunk.chunk_id,
                            "document_id": chunk.document_id,
                            "pass_id": pass_id,
                            "chunk_text": chunk.text,
                            "previous_context": chunk.previous_context if turn == 1 else refined,
                            "task_instructions": task_instructions,
                            "turn": turn,
                        }
                        report = await _arun_with_retries(
                            self._runtime_config.retry,
                            lambda: session.arun(
                                payload,
                                response_schema=SessionRefinementResult,
                                stream=False,
                            ),
                            session.aresume,
                            context,
                            "Refinement",
                        )
                        if report.data is None:
                            raise RuntimeIntegrationError(
                                "Refinement completed without structured data", context=context
                            )
                        try:
                            candidate = SessionRefinementResult.model_validate(
                                report.data
                            ).refinement_context.strip()
                        except ValidationError as exc:
                            raise RuntimeIntegrationError(
                                "Refinement response validation failed", context=context
                            ) from exc
                        if not candidate:
                            break
                        refined = candidate
                    if refined:
                        contexts[chunk.chunk_id] = refined[: config.context_chars]
            finally:
                session.close()
        return contexts

    def _flow(
        self,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
        refinement_contexts: dict[str, str],
    ) -> tuple[Any, Any, dict[str, str]]:
        steps: list[Any] = []
        worker_names: dict[str, str] = {}
        for chunk in chunks:
            prompt = self._prompt_compiler.compile(
                self._schema_set,
                chunk,
                pass_id,
                instructions=task_instructions,
                refinement_context=refinement_contexts.get(chunk.chunk_id),
            )
            worker_name = f"ExtractorWorker:{chunk.chunk_id}"
            worker = self._blackgeorge.Worker(
                name=worker_name,
                instructions=prompt.system,
            )
            chunk_job = self._blackgeorge.Job(
                input=prompt.user,
                response_schema=self._response_schema,
            )

            def job_builder(_context: Any, job: Any = chunk_job) -> Any:
                return job

            steps.append(self._Step(worker, name=chunk.chunk_id, job_builder=job_builder))
            worker_names[chunk.chunk_id] = worker_name

        flow = self._desk.flow([self._Parallel(*steps)], name=f"sourcery-flow:{run_id}:p{pass_id}")
        job = self._blackgeorge.Job(
            input={
                "run_id": run_id,
                "pass_id": pass_id,
                "chunk_ids": [chunk.chunk_id for chunk in chunks],
            }
        )
        return flow, job, worker_names

    def _flow_reports(
        self,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        worker_names: dict[str, str],
        report: Any,
    ) -> list[ChunkExtractionReport]:
        data = _flow_data(report.data, len(chunks))
        raw_run_id = getattr(report, "run_id", None)
        if not isinstance(raw_run_id, str) or not raw_run_id:
            raise RuntimeIntegrationError("BlackGeorge flow report is missing a run id")
        events = self._desk.run_store.get_events(raw_run_id)
        worker_sources = set(worker_names.values())
        chunk_sources = set(worker_names)
        shared = [
            event_to_record(event)
            for event in events
            if getattr(event, "source", "") not in worker_sources | chunk_sources
        ]
        errors = [str(error) for error in getattr(report, "errors", []) or []]

        results: list[ChunkExtractionReport] = []
        for index, chunk in enumerate(chunks):
            worker_name = worker_names[chunk.chunk_id]
            chunk_events = [
                event_to_record(event)
                for event in events
                if str(getattr(event, "source", "")) in {chunk.chunk_id, worker_name}
                or dict(getattr(event, "payload", {}) or {}).get("chunk_id") == chunk.chunk_id
            ]
            results.append(
                ChunkExtractionReport(
                    run_id=run_id,
                    pass_id=pass_id,
                    chunk=chunk,
                    candidates=parse_candidates_from_structured_data(data[index]),
                    warnings=errors if index == 0 else [],
                    events=(shared + chunk_events) if index == 0 else chunk_events,
                    worker_name=worker_name,
                    model=self._runtime_config.model,
                    raw_run_id=raw_run_id,
                )
            )
        return results

    def _reconciliation_workforce(
        self,
        run_id: str,
        document: SourceDocument,
        extractions: list[AlignedExtraction],
        task_instructions: str,
    ) -> tuple[Any, Any, ErrorContext]:
        from blackgeorge.collaboration import (
            Blackboard,
            blackboard_read_tool,
            blackboard_write_tool,
        )

        blackboard = Blackboard()
        coreference_worker = self._blackgeorge.Worker(
            name=COREFERENCE_WORKER,
            instructions=(
                "Cluster equivalent entity mentions across all chunks. Write an object to "
                "blackboard key 'coreference_clusters' using blackboard_write. Then return "
                "mode='coreference' with a compact summary."
            ),
            tools=[blackboard_write_tool(blackboard, author=COREFERENCE_WORKER)],
        )
        resolver_worker = self._blackgeorge.Worker(
            name=RESOLVER_WORKER,
            instructions=(
                "Read blackboard key 'coreference_clusters' and produce canonical resolved "
                "entities and claims. Return mode='resolver', keep_indices, and canonical_claims."
            ),
            tools=[blackboard_read_tool(blackboard)],
        )
        workforce = self._blackgeorge.Workforce(
            [coreference_worker, resolver_worker],
            mode="collaborate",
            name=f"sourcery-reconcile:{run_id}:{document.document_id}",
            blackboard=blackboard,
        )
        job = self._blackgeorge.Job(
            input={
                "document_id": document.document_id,
                "task_instructions": task_instructions,
                "reconciliation_config": self._runtime_config.reconciliation.model_dump(
                    mode="json"
                ),
                "extractions": [
                    {
                        "index": index,
                        "entity": extraction.entity,
                        "text": extraction.text,
                        "alignment_status": extraction.alignment_status,
                        "confidence": extraction.confidence,
                        "char_start": extraction.char_start,
                        "char_end": extraction.char_end,
                        "attributes": _attributes(extraction.attributes),
                    }
                    for index, extraction in enumerate(extractions)
                ],
            },
            response_schema=ReconciliationWorkerOutput,
        )
        context = ErrorContext(
            run_id=run_id,
            model=self._runtime_config.model,
            provider=self._runtime_config.model.partition("/")[0],
        )
        return workforce, job, context

    def _reconciliation_report(
        self,
        document: SourceDocument,
        extractions: list[AlignedExtraction],
        report: Any,
        context: ErrorContext,
    ) -> DocumentReconciliationReport:
        raw_run_id = getattr(report, "run_id", None)
        if not isinstance(raw_run_id, str) or not raw_run_id:
            raise RuntimeIntegrationError(
                "BlackGeorge reconciliation report is missing a run id", context=context
            )
        warnings = [str(error) for error in getattr(report, "errors", []) or []]
        events = [event_to_record(event) for event in self._desk.run_store.get_events(raw_run_id)]
        resolver_data: Any | None = None
        if isinstance(report.data, list):
            for item in report.data:
                if isinstance(item, dict) and item.get("worker") == RESOLVER_WORKER:
                    resolver_data = item.get("data")
                    break
        if resolver_data is None:
            return DocumentReconciliationReport(
                document_id=document.document_id,
                reconciled_extractions=extractions,
                warnings=warnings + ["Resolver worker output missing from reconciliation run"],
                events=events,
                raw_run_id=raw_run_id,
            )
        try:
            output = ReconciliationWorkerOutput.model_validate(resolver_data)
        except ValidationError as exc:
            raise RuntimeIntegrationError(
                "Resolver response validation failed", context=context
            ) from exc
        if output.mode != "resolver":
            raise RuntimeIntegrationError(
                "Resolver worker returned the wrong response mode", context=context
            )
        indices = _valid_indices(output.keep_indices, len(extractions))
        if not indices:
            indices = list(range(len(extractions)))
        return DocumentReconciliationReport(
            document_id=document.document_id,
            reconciled_extractions=[extractions[index] for index in indices],
            canonical_claims=_worker_claims(
                self._runtime_config.reconciliation,
                document.document_id,
                extractions,
                output,
                set(indices),
            ),
            warnings=warnings,
            events=events,
            raw_run_id=raw_run_id,
        )
