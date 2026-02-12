from __future__ import annotations

from collections.abc import Iterable

from sourcery.contracts import ChunkExtractionReport, EventRecord, ExtractionRunTrace


class RunTraceCollector:
    def __init__(self, *, run_id: str, model: str) -> None:
        self._run_id = run_id
        self._model = model
        self._events: list[EventRecord] = []

    def add_events(self, events: Iterable[EventRecord]) -> None:
        self._events.extend(events)

    def add_report_events(self, report: ChunkExtractionReport) -> None:
        self._events.extend(report.events)

    def finalize(self, *, chunk_ids: list[str], pass_ids: list[int]) -> ExtractionRunTrace:
        return ExtractionRunTrace(
            run_id=self._run_id,
            model=self._model,
            chunk_ids=chunk_ids,
            pass_ids=pass_ids,
            events=self._events,
        )
