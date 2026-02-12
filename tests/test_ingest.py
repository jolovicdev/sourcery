from __future__ import annotations

from pathlib import Path

import pytest

from sourcery.exceptions import SourceryIngestionError
from sourcery.ingest import (
    load_html_document,
    load_source_document,
    load_source_documents,
)


def test_load_source_document_from_inline_text() -> None:
    document = load_source_document("Alice runs Acme.")
    assert document.text == "Alice runs Acme."
    assert document.metadata["source_type"] == "inline_text"


def test_load_html_document_strips_tags() -> None:
    document = load_html_document(
        "<html><body><h1>Title</h1><p>Alice at Acme.</p></body></html>", raw_html=True
    )
    assert "Title" in document.text
    assert "Alice at Acme." in document.text


def test_load_source_document_from_file(tmp_path: Path) -> None:
    path = tmp_path / "sample.txt"
    path.write_text("Sample document text.", encoding="utf-8")
    document = load_source_document(path)

    assert document.text == "Sample document text."
    assert document.metadata["source_type"] == "text_file"
    assert document.metadata["source"].endswith("sample.txt")


def test_load_source_documents_assigns_deterministic_ids(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_text("A", encoding="utf-8")

    docs = load_source_documents([path, "B"])
    assert docs[0].document_id == "doc_0"
    assert docs[1].document_id == "doc_1"


def test_load_source_document_rejects_empty_inline_text() -> None:
    with pytest.raises(SourceryIngestionError):
        load_source_document("   ")
