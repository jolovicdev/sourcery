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


class WrongAttributes(BaseModel):
    title: str


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


def test_partial_alignment_rejects_single_token_fragment() -> None:
    text = "The report names no monarch."
    chunk = TextChunk(
        chunk_id="c-partial-negative",
        document_id="d1",
        pass_id=1,
        order_index=0,
        text=text,
        char_start=0,
        char_end=len(text),
    )

    result = align_candidates(
        candidates=[
            ExtractionCandidate(
                entity="person",
                text="the Queen of Hearts",
                attributes={"role": "monarch"},
            )
        ],
        chunk=chunk,
        schema=_schema(),
        options=ExtractOptions(
            enable_fuzzy_alignment=False,
            accept_partial_exact=True,
            allow_unresolved=True,
        ),
        provenance_base=_provenance(),
    )

    assert result.unresolved_count == 1
    assert result.aligned[0].alignment_status == "unresolved"


def test_partial_alignment_uses_longest_contiguous_token_sequence() -> None:
    text = "Queen of Hearts entered."
    chunk = TextChunk(
        chunk_id="c-partial-positive",
        document_id="d1",
        pass_id=1,
        order_index=0,
        text=text,
        char_start=0,
        char_end=len(text),
    )

    result = align_candidates(
        candidates=[
            ExtractionCandidate(
                entity="person",
                text="the Queen of Hearts",
                attributes={"role": "monarch"},
            )
        ],
        chunk=chunk,
        schema=_schema(),
        options=ExtractOptions(
            enable_fuzzy_alignment=False,
            accept_partial_exact=True,
        ),
        provenance_base=_provenance(),
    )

    assert len(result.aligned) == 1
    assert result.aligned[0].alignment_status == "partial"
    assert (result.aligned[0].char_start, result.aligned[0].char_end) == (0, 15)


def test_repeated_candidates_align_to_distinct_source_occurrences() -> None:
    chunk = TextChunk(
        chunk_id="c-repeat",
        document_id="d1",
        pass_id=1,
        order_index=0,
        text="Alice met Alice.",
        char_start=10,
        char_end=26,
    )
    candidates = [
        ExtractionCandidate(entity="person", text="Alice", attributes={"role": "CEO"}),
        ExtractionCandidate(entity="person", text="Alice", attributes={"role": "CEO"}),
    ]

    result = align_candidates(
        candidates=candidates,
        chunk=chunk,
        schema=_schema(),
        options=ExtractOptions(),
        provenance_base=_provenance(),
    )

    assert [(item.char_start, item.char_end) for item in result.aligned] == [
        (10, 15),
        (20, 25),
    ]


def test_unknown_entities_and_wrong_attribute_models_are_rejected() -> None:
    candidates = [
        ExtractionCandidate(entity="company", text="Alice", attributes={}),
        ExtractionCandidate(
            entity="person",
            text="Alice",
            attributes=WrongAttributes(title="CEO"),
        ),
    ]

    result = align_candidates(
        candidates=candidates,
        chunk=_chunk(),
        schema=_schema(),
        options=ExtractOptions(allow_unresolved=True),
        provenance_base=_provenance(),
    )

    assert result.aligned == []
    assert len(result.warnings) == 2
