from __future__ import annotations

from pathlib import Path

from sourcery.contracts import ExtractRequest
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
