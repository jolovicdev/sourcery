from __future__ import annotations

from pathlib import Path
import re

import pytest

from sourcery.contracts import DocumentResult, ExtractRequest
from sourcery.io import (
    load_document_results_jsonl,
    render_document_html,
    render_reviewer_html,
    save_extract_result_jsonl,
    visualize,
    write_reviewer_html,
)
from sourcery.runtime.engine import SourceryEngine


def test_jsonl_roundtrip(tmp_path: Path, extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    result = engine.extract(extract_request)

    dumped = result.model_dump(mode="json")
    assert dumped["documents"][0]["extractions"][0]["attributes"] == {"role": "CEO"}

    path = tmp_path / "result.jsonl"
    save_extract_result_jsonl(result, path)
    loaded = load_document_results_jsonl(path)

    assert len(loaded) == len(result.documents)
    assert loaded[0].document_id == result.documents[0].document_id


def test_html_visualization_contains_marks(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    result = engine.extract(extract_request)

    html = render_document_html(result.documents[0])
    assert "<mark" in html
    assert "sxPlayPause" in html


def test_visualize_from_jsonl_path(tmp_path: Path, extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    result = engine.extract(extract_request)

    path = tmp_path / "result.jsonl"
    save_extract_result_jsonl(result, path)
    html = visualize(path, return_html_obj=False)

    assert "sx-wrapper" in html
    assert "sxNext" in html


def test_reviewer_html_contains_controls(tmp_path: Path, extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    engine = SourceryEngine(runtime_factory=FakeRuntime)
    result = engine.extract(extract_request)

    html = render_reviewer_html(result.documents[0])
    assert "sr-search" in html
    assert "sr-approve-filtered" in html
    assert "sr-export-jsonl" in html

    output_path = tmp_path / "reviewer.html"
    write_reviewer_html(result.documents[0], output_path)
    assert output_path.exists()


def test_jsonl_roundtrip_with_canonical_claims(
    tmp_path: Path, extract_request: ExtractRequest
) -> None:
    from tests.conftest import FakeReconciliationRuntime

    extract_request.runtime.reconciliation.enabled = True
    engine = SourceryEngine(runtime_factory=FakeReconciliationRuntime)
    result = engine.extract(extract_request)

    path = tmp_path / "result-canonical.jsonl"
    save_extract_result_jsonl(result, path)
    loaded = load_document_results_jsonl(path)

    assert loaded[0].canonical_claims
    assert (
        loaded[0].canonical_claims[0].claim_id == result.documents[0].canonical_claims[0].claim_id
    )


def test_html_renderers_escape_script_data(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    result = SourceryEngine(runtime_factory=FakeRuntime).extract(extract_request)
    document = result.documents[0]
    extraction = document.extractions[0].model_copy(
        update={"attributes": {"payload": "</script><script>alert(1)</script>"}}
    )
    malicious = DocumentResult(
        document_id=document.document_id,
        text=document.text,
        extractions=[extraction],
    )

    viewer = render_document_html(malicious)
    reviewer = render_reviewer_html(malicious)

    assert "</script><script>alert(1)</script>" not in viewer
    assert "</script><script>alert(1)</script>" not in reviewer
    assert "\\u003c/script>" in viewer
    assert "\\u003c/script>" in reviewer


def test_visualization_uses_one_stable_color_per_entity(extract_request: ExtractRequest) -> None:
    from tests.conftest import FakeRuntime

    result = SourceryEngine(runtime_factory=FakeRuntime).extract(extract_request)
    first = result.documents[0].extractions[0]
    text = f"{first.text} {first.text}"
    second = first.model_copy(update={"char_start": len(first.text) + 1, "char_end": len(text)})
    document = DocumentResult(
        document_id="same-color",
        text=text,
        extractions=[
            first.model_copy(update={"char_start": 0, "char_end": len(first.text)}),
            second,
        ],
    )

    colors = re.findall(
        r"<mark class='sx-highlight'[^>]+background:(#[0-9a-f]+)", render_document_html(document)
    )

    assert len(colors) == 2
    assert colors[0] == colors[1]


def test_jsonl_reports_invalid_line_number(tmp_path: Path) -> None:
    path = tmp_path / "invalid.jsonl"
    path.write_text("\nnot-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"invalid\.jsonl:2"):
        load_document_results_jsonl(path)
