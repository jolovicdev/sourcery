from __future__ import annotations

from pydantic import BaseModel

from sourcery.contracts import AlignedExtraction, ExtractionProvenance
from sourcery.pipeline import merge_non_overlapping


class Attr(BaseModel):
    value: str


def _prov() -> ExtractionProvenance:
    return ExtractionProvenance(
        run_id="r",
        pass_id=1,
        chunk_id="c",
        worker_name="w",
        model="m",
    )


def _aligned(
    entity: str, start: int, end: int, *, pass_id: int = 1, confidence: float = 0.9
) -> AlignedExtraction:
    provenance = _prov().model_copy(update={"pass_id": pass_id})
    return AlignedExtraction(
        entity=entity,
        text=entity,
        attributes=Attr(value="x"),
        char_start=start,
        char_end=end,
        token_start=None,
        token_end=None,
        alignment_status="exact",
        confidence=confidence,
        provenance=provenance,
    )


def test_merges_non_overlapping() -> None:
    existing = [_aligned("a", 0, 5)]
    incoming = [_aligned("b", 6, 9)]
    merged, additions = merge_non_overlapping(existing, incoming)
    assert additions == 1
    assert len(merged) == 2


def test_rejects_overlap() -> None:
    existing = [_aligned("a", 0, 5)]
    incoming = [_aligned("b", 4, 8)]
    merged, additions = merge_non_overlapping(existing, incoming)
    assert additions == 0
    assert len(merged) == 1


def test_overlap_earlier_pass_wins() -> None:
    existing = [_aligned("a", 0, 5, pass_id=1, confidence=0.3)]
    incoming = [_aligned("b", 0, 5, pass_id=2, confidence=0.99)]
    merged, additions = merge_non_overlapping(existing, incoming)
    assert additions == 0
    assert len(merged) == 1
    assert merged[0].entity == "a"


def test_overlap_higher_confidence_wins_when_same_pass() -> None:
    existing = [_aligned("a", 0, 5, pass_id=1, confidence=0.2)]
    incoming = [_aligned("b", 0, 5, pass_id=1, confidence=0.95)]
    merged, additions = merge_non_overlapping(existing, incoming)
    assert additions == 1
    assert len(merged) == 1
    assert merged[0].entity == "b"


def test_unresolved_attribute_variants_do_not_accumulate_across_passes() -> None:
    first = AlignedExtraction(
        entity="missing",
        text="missing",
        attributes=Attr(value="x"),
        char_start=0,
        char_end=0,
        alignment_status="unresolved",
        confidence=0.9,
        provenance=_prov(),
    )
    second = first.model_copy(
        update={
            "attributes": Attr(value="y"),
            "provenance": _prov().model_copy(update={"pass_id": 2}),
        }
    )

    merged, additions = merge_non_overlapping([first], [second])

    assert additions == 0
    assert merged == [first]


def test_distinct_unresolved_texts_remain_separate() -> None:
    first = AlignedExtraction(
        entity="missing",
        text="first missing value",
        attributes=Attr(value="x"),
        char_start=0,
        char_end=0,
        alignment_status="unresolved",
        confidence=0.9,
        provenance=_prov(),
    )
    second = first.model_copy(
        update={
            "text": "second missing value",
            "attributes": Attr(value="y"),
            "provenance": _prov().model_copy(update={"pass_id": 2}),
        }
    )

    merged, additions = merge_non_overlapping([first], [second])

    assert additions == 1
    assert merged == [first, second]
