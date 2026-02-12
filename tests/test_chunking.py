from __future__ import annotations

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
