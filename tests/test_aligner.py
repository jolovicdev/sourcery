from __future__ import annotations

from pydantic import BaseModel

from sourcery.contracts import (
    EntitySchemaSet,
    EntitySpec,
    ExtractOptions,
    ExtractionCandidate,
    ExtractionProvenance,
    TextChunk,
)
from sourcery.pipeline import align_candidates


class Person(BaseModel):
    role: str


def _schema() -> EntitySchemaSet:
    return EntitySchemaSet(entities=[EntitySpec(name="person", attributes_model=Person)])


def _chunk() -> TextChunk:
    return TextChunk(
        chunk_id="c1",
        document_id="d1",
        pass_id=1,
        order_index=0,
        text="Alice leads product.",
        char_start=0,
        char_end=20,
        token_start=0,
        token_end=4,
    )


def _provenance() -> ExtractionProvenance:
    return ExtractionProvenance(
        run_id="run-1",
        pass_id=1,
        chunk_id="c1",
        worker_name="ExtractorWorker",
        model="openai/gpt-5-nano",
    )


def test_exact_alignment() -> None:
    result = align_candidates(
        candidates=[ExtractionCandidate(entity="person", text="Alice", attributes={"role": "CEO"})],
        chunk=_chunk(),
        schema=_schema(),
        options=ExtractOptions(),
        provenance_base=_provenance(),
    )
    assert len(result.aligned) == 1
    assert result.aligned[0].alignment_status == "exact"


def test_unresolved_rejected_by_default() -> None:
    result = align_candidates(
        candidates=[ExtractionCandidate(entity="person", text="Bob", attributes={"role": "CEO"})],
        chunk=_chunk(),
        schema=_schema(),
        options=ExtractOptions(),
        provenance_base=_provenance(),
    )
    assert result.unresolved_count == 1
    assert result.aligned == []


def test_unresolved_allowed() -> None:
    options = ExtractOptions(allow_unresolved=True)
    result = align_candidates(
        candidates=[ExtractionCandidate(entity="person", text="Bob", attributes={"role": "CEO"})],
        chunk=_chunk(),
        schema=_schema(),
        options=options,
        provenance_base=_provenance(),
    )
    assert len(result.aligned) == 1
    assert result.aligned[0].alignment_status == "unresolved"
