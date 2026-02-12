from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import Path
from typing import Any, cast

from sourcery.contracts import DocumentResult, ExtractResult


def save_extract_result_jsonl(result: ExtractResult, path: str | Path) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    with file_path.open("w", encoding="utf-8") as handle:
        for document in result.documents:
            row = {
                "document_id": document.document_id,
                "text": document.text,
                "extractions": [
                    {
                        "entity": extraction.entity,
                        "text": extraction.text,
                        "attributes": _dump_attributes(extraction.attributes),
                        "char_start": extraction.char_start,
                        "char_end": extraction.char_end,
                        "token_start": extraction.token_start,
                        "token_end": extraction.token_end,
                        "alignment_status": extraction.alignment_status,
                        "confidence": extraction.confidence,
                        "provenance": extraction.provenance.model_dump(mode="json"),
                    }
                    for extraction in document.extractions
                ],
                "canonical_claims": [
                    {
                        "claim_id": claim.claim_id,
                        "entity": claim.entity,
                        "canonical_text": claim.canonical_text,
                        "mention_count": claim.mention_count,
                        "extraction_indices": claim.extraction_indices,
                        "confidence": claim.confidence,
                        "attributes": claim.attributes,
                    }
                    for claim in document.canonical_claims
                ],
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def iter_document_rows(path: str | Path) -> Iterator[dict[str, Any]]:
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            yield json.loads(stripped)


def load_document_results_jsonl(path: str | Path) -> list[DocumentResult]:
    documents: list[DocumentResult] = []
    for row in iter_document_rows(path):
        documents.append(DocumentResult.model_validate(row))
    return documents


def _dump_attributes(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump(mode="json")
            if isinstance(dumped, dict):
                return cast(dict[str, Any], dumped)
        except Exception:
            pass
    return cast(dict[str, Any], dict(value))
