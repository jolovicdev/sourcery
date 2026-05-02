from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from sourcery.contracts import RuntimeConfig
from sourcery.exceptions import SourceryIngestionError
from sourcery.ingest.vlm_ocr import BlackGeorgeVLMOCRBackend, VLMOCRBackend
from sourcery.ingest.loaders import load_vlm_ocr_document, load_vlm_ocr_documents


class FakeVLMBackend:
    def __init__(self, text: str = "Extracted text from image.") -> None:
        self.text = text
        self.calls: list[dict[str, object]] = []

    def extract_text(self, *, image_path: Path, prompt: str | None = None) -> str:
        self.calls.append({"image_path": image_path, "prompt": prompt})
        return self.text


class EmptyVLMBackend:
    def extract_text(self, *, image_path: Path, prompt: str | None = None) -> str:
        return "   "


def test_fake_backend_satisfies_protocol() -> None:
    backend = FakeVLMBackend()
    assert isinstance(backend, VLMOCRBackend)


def test_load_vlm_ocr_document_returns_source_document(tmp_path: Path) -> None:
    image = tmp_path / "scan.png"
    image.write_text("fake image bytes")
    backend = FakeVLMBackend("Hello from OCR")

    doc = load_vlm_ocr_document(image, backend=backend)

    assert doc.text == "Hello from OCR"
    assert doc.metadata["source_type"] == "vlm_ocr"
    assert str(image) in doc.metadata["source"]


def test_load_vlm_ocr_document_passes_prompt(tmp_path: Path) -> None:
    image = tmp_path / "scan.png"
    image.write_text("fake image bytes")
    backend = FakeVLMBackend()

    load_vlm_ocr_document(image, backend=backend, prompt="Extract tables only.")
    assert backend.calls[0]["prompt"] == "Extract tables only."


def test_load_vlm_ocr_document_missing_file_raises() -> None:
    backend = FakeVLMBackend()
    with pytest.raises(SourceryIngestionError, match="does not exist"):
        load_vlm_ocr_document(Path("/nonexistent/scan.png"), backend=backend)


def test_load_vlm_ocr_document_empty_result_raises(tmp_path: Path) -> None:
    image = tmp_path / "scan.png"
    image.write_text("fake image bytes")
    with pytest.raises(SourceryIngestionError, match="empty text"):
        load_vlm_ocr_document(image, backend=EmptyVLMBackend())


def test_load_vlm_ocr_documents_batch(tmp_path: Path) -> None:
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    a.write_text("a")
    b.write_text("b")
    backend = FakeVLMBackend("text")

    docs = load_vlm_ocr_documents([a, b], backend=backend)

    assert len(docs) == 2
    assert docs[0].document_id == "ocr_doc_0"
    assert docs[1].document_id == "ocr_doc_1"
    assert len(backend.calls) == 2


def test_load_vlm_ocr_document_uses_stem_as_document_id(tmp_path: Path) -> None:
    image = tmp_path / "invoice-42.png"
    image.write_text("fake")
    backend = FakeVLMBackend("text")
    doc = load_vlm_ocr_document(image, backend=backend)
    assert doc.document_id == "invoice-42"


def test_blackgeorge_backend_creates_multimodal_job(tmp_path: Path) -> None:
    image = tmp_path / "scan.png"
    image.write_bytes(b"\x89PNG\x0d\x0a")
    config = RuntimeConfig(model="gemini/gemini-2.5-flash", temperature=0.0)

    with mock.patch("blackgeorge.encode_file", return_value="data:image/png;base64,ZmFrZQ=="):
        with mock.patch("blackgeorge.Desk") as mock_desk_class:
            mock_desk = mock_desk_class.return_value
            mock_report = mock.MagicMock()
            mock_report.content = "OCR extracted text"
            mock_desk.run.return_value = mock_report

            with mock.patch("blackgeorge.Worker") as mock_worker_class:
                with mock.patch("blackgeorge.Job") as mock_job_class:
                    mock_job_instance = mock_job_class.return_value
                    mock_worker_instance = mock_worker_class.return_value

                    backend = BlackGeorgeVLMOCRBackend(config)
                    result = backend.extract_text(image_path=image)

    assert result == "OCR extracted text"
    mock_job_class.assert_called_once()
    job_input = mock_job_class.call_args[1]["input"]
    assert isinstance(job_input, list)
    assert job_input[0]["type"] == "image_url"
    assert job_input[0]["image_url"]["url"] == "data:image/png;base64,ZmFrZQ=="
    assert job_input[1]["type"] == "text"
    mock_desk.run.assert_called_once_with(mock_worker_instance, mock_job_instance)


def test_blackgeorge_backend_uses_custom_prompt(tmp_path: Path) -> None:
    image = tmp_path / "scan.png"
    image.write_bytes(b"\x89PNG")
    config = RuntimeConfig(model="gemini/gemini-2.5-flash")

    with mock.patch("blackgeorge.encode_file", return_value="data:image/png;base64,QQ=="):
        with mock.patch("blackgeorge.Desk") as mock_desk_class:
            mock_desk = mock_desk_class.return_value
            mock_report = mock.MagicMock()
            mock_report.content = "text"
            mock_desk.run.return_value = mock_report

            with mock.patch("blackgeorge.Worker") as mock_worker_class:
                with mock.patch("blackgeorge.Job") as mock_job_class:
                    backend = BlackGeorgeVLMOCRBackend(
                        config, default_prompt="Default prompt"
                    )
                    backend.extract_text(image_path=image, prompt="Custom request")

    job_input = mock_job_class.call_args[1]["input"]
    text_block = next(b for b in job_input if b["type"] == "text")
    assert text_block["text"] == "Custom request"
    assert mock_worker_class.call_args[1]["instructions"] == "Custom request"


def test_blackgeorge_backend_empty_content_raises(tmp_path: Path) -> None:
    image = tmp_path / "scan.png"
    image.write_bytes(b"\x89PNG")
    config = RuntimeConfig(model="gemini/gemini-2.5-flash")

    with mock.patch("blackgeorge.encode_file", return_value="data:image/png;base64,QQ=="):
        with mock.patch("blackgeorge.Desk") as mock_desk_class:
            mock_desk = mock_desk_class.return_value
            mock_report = mock.MagicMock()
            mock_report.content = None
            mock_report.data = None
            mock_report.errors = ["API error"]
            mock_desk.run.return_value = mock_report

            with mock.patch("blackgeorge.Worker"), mock.patch("blackgeorge.Job"):
                backend = BlackGeorgeVLMOCRBackend(config)
                with pytest.raises(SourceryIngestionError, match="empty text"):
                    backend.extract_text(image_path=image)
