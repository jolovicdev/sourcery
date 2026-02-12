from __future__ import annotations

import asyncio

import sourcery
from sourcery.contracts import ExtractRequest, ExtractionTask, RuntimeConfig
from sourcery.runtime.engine import SourceryEngine


def test_top_level_extract(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    result = sourcery.extract(extract_request, engine=engine)
    assert result.documents


def test_top_level_aextract(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    result = asyncio.run(sourcery.aextract(extract_request, engine=engine))
    assert result.metrics.documents_total == 1


def test_extract_from_sources_uses_ingestion(task: ExtractionTask) -> None:
    from tests.conftest import FakeRuntime

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    result = sourcery.extract_from_sources(
        "Alice is the CEO of Acme.",
        task=task,
        runtime=RuntimeConfig(model="openai/gpt-5-nano"),
        engine=engine,
    )
    assert result.documents
