from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from typing import Protocol
from typing import runtime_checkable

from sourcery.contracts import (
    AlignedExtraction,
    ChunkExtractionReport,
    DocumentReconciliationReport,
    EventRecord,
    RuntimeConfig,
    SourceDocument,
    TextChunk,
)


class ChunkRuntime(Protocol):
    def run_pass(
        self,
        *,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
        batch_concurrency: int,
    ) -> list[ChunkExtractionReport]: ...

    async def arun_pass(
        self,
        *,
        run_id: str,
        pass_id: int,
        chunks: Sequence[TextChunk],
        task_instructions: str,
        batch_concurrency: int,
    ) -> list[ChunkExtractionReport]: ...

    def replay_run(self, raw_run_id: str) -> tuple[dict[str, Any] | None, list[EventRecord]]: ...


class RuntimeFactory(Protocol):
    def __call__(
        self, runtime_config: RuntimeConfig, schema_set: object, prompt_compiler: object
    ) -> ChunkRuntime: ...


@runtime_checkable
class DocumentReconciliationRuntime(Protocol):
    def reconcile_document(
        self,
        *,
        run_id: str,
        document: SourceDocument,
        extractions: Sequence[AlignedExtraction],
        task_instructions: str,
    ) -> DocumentReconciliationReport: ...
