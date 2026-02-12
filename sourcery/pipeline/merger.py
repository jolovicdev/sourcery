from __future__ import annotations

from collections.abc import Iterable

from sourcery.contracts import AlignedExtraction


def _overlaps(a: AlignedExtraction, b: AlignedExtraction) -> bool:
    if a.alignment_status == "unresolved" or b.alignment_status == "unresolved":
        return False
    return a.char_start < b.char_end and b.char_start < a.char_end


def _confidence_score(extraction: AlignedExtraction) -> float:
    if extraction.confidence is None:
        return -1.0
    return extraction.confidence


def _priority_key(extraction: AlignedExtraction, source_order: int) -> tuple[object, ...]:
    return (
        extraction.provenance.pass_id,
        -_confidence_score(extraction),
        extraction.char_start,
        extraction.char_end,
        extraction.entity,
        extraction.text,
        source_order,
    )


def _sort_key(extraction: AlignedExtraction) -> tuple[object, ...]:
    return (
        extraction.char_start,
        extraction.char_end,
        extraction.provenance.pass_id,
        extraction.entity,
        extraction.text,
        -_confidence_score(extraction),
    )


def merge_non_overlapping(
    existing: list[AlignedExtraction],
    incoming: Iterable[AlignedExtraction],
) -> tuple[list[AlignedExtraction], int]:
    merged = list(existing)
    additions = 0

    for extraction in incoming:
        overlapping_indices = [
            index for index, prior in enumerate(merged) if _overlaps(extraction, prior)
        ]
        if not overlapping_indices:
            merged.append(extraction)
            additions += 1
            continue

        contenders: list[tuple[AlignedExtraction, int]] = [
            (merged[index], 0) for index in overlapping_indices
        ]
        contenders.append((extraction, 1))
        winner, source_order = min(contenders, key=lambda pair: _priority_key(pair[0], pair[1]))

        if source_order == 0:
            continue

        for index in reversed(overlapping_indices):
            del merged[index]
        merged.append(winner)
        additions += 1

    merged.sort(key=_sort_key)
    return merged, additions
