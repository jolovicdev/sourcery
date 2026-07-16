from __future__ import annotations

import pytest

from sourcery.contracts import SourceDocument
from sourcery.pipeline import plan_chunks


def test_chunk_planner_is_deterministic() -> None:
    doc = SourceDocument(document_id="doc-1", text="A. B. C. D.")
    chunks_1 = plan_chunks([doc], pass_id=1, max_chunk_chars=4, context_window_chars=2)
    chunks_2 = plan_chunks([doc], pass_id=1, max_chunk_chars=4, context_window_chars=2)

    assert [chunk.model_dump() for chunk in chunks_1] == [chunk.model_dump() for chunk in chunks_2]


def test_chunk_planner_preserves_offsets() -> None:
    text = "Alice works at Acme. Alice leads strategy."
    doc = SourceDocument(document_id="doc-2", text=text)
    chunks = plan_chunks([doc], pass_id=1, max_chunk_chars=24, context_window_chars=10)

    reconstructed = "".join(chunk.text for chunk in chunks)
    assert reconstructed.replace(" ", "") in text.replace(" ", "")
    assert all(chunk.char_start < chunk.char_end for chunk in chunks)
    assert chunks[0].previous_context is None
    assert chunks[-1].previous_context is not None


def test_chunk_planner_carries_document_context_into_every_chunk() -> None:
    document = SourceDocument(
        document_id="doc-context",
        text="Alpha sentence. Beta sentence.",
        additional_context="The document describes Project Atlas.",
    )

    chunks = plan_chunks(
        [document],
        pass_id=1,
        max_chunk_chars=16,
        context_window_chars=4,
    )

    assert len(chunks) == 2
    assert all("Project Atlas" in (chunk.previous_context or "") for chunk in chunks)
    assert "Previous chunk" not in (chunks[0].previous_context or "")
    assert "Previous chunk" in (chunks[1].previous_context or "")


@pytest.mark.parametrize(
    ("pass_id", "max_chunk_chars", "context_window_chars"),
    [(0, 10, 0), (1, 0, 0), (1, 10, -1)],
)
def test_chunk_planner_rejects_invalid_direct_arguments(
    pass_id: int, max_chunk_chars: int, context_window_chars: int
) -> None:
    document = SourceDocument(text="text")

    with pytest.raises(ValueError):
        plan_chunks(
            [document],
            pass_id=pass_id,
            max_chunk_chars=max_chunk_chars,
            context_window_chars=context_window_chars,
        )
