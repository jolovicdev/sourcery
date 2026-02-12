from __future__ import annotations

from pathlib import Path

from sourcery.contracts import (
    ExtractOptions,
    ExtractRequest,
    ExtractResult,
    ExtractionTask,
    RuntimeConfig,
    SourceDocument,
)
from sourcery.ingest import load_source_documents
from sourcery.runtime.engine import SourceryEngine


def extract(request: ExtractRequest, engine: SourceryEngine | None = None) -> ExtractResult:
    selected_engine = engine or SourceryEngine()
    return selected_engine.extract(request)


async def aextract(request: ExtractRequest, engine: SourceryEngine | None = None) -> ExtractResult:
    selected_engine = engine or SourceryEngine()
    return await selected_engine.aextract(request)


def extract_from_sources(
    sources: list[SourceDocument | str | Path] | SourceDocument | str | Path,
    *,
    task: ExtractionTask,
    runtime: RuntimeConfig,
    options: ExtractOptions | None = None,
    engine: SourceryEngine | None = None,
) -> ExtractResult:
    request = ExtractRequest(
        documents=load_source_documents(sources),
        task=task,
        runtime=runtime,
        options=options or ExtractOptions(),
    )
    return extract(request=request, engine=engine)


async def aextract_from_sources(
    sources: list[SourceDocument | str | Path] | SourceDocument | str | Path,
    *,
    task: ExtractionTask,
    runtime: RuntimeConfig,
    options: ExtractOptions | None = None,
    engine: SourceryEngine | None = None,
) -> ExtractResult:
    request = ExtractRequest(
        documents=load_source_documents(sources),
        task=task,
        runtime=runtime,
        options=options or ExtractOptions(),
    )
    return await aextract(request=request, engine=engine)
