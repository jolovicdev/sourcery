from __future__ import annotations

from collections.abc import Sequence
from html.parser import HTMLParser
import importlib
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from sourcery.contracts import SourceDocument
from sourcery.exceptions import SourceryDependencyError, SourceryIngestionError

_TEXT_FILE_SUFFIXES = {".txt", ".md", ".rst", ".csv", ".json", ".jsonl", ".yaml", ".yml"}
_HTML_SUFFIXES = {".html", ".htm"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return "\n".join(self.parts)


def _normalize_metadata(metadata: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    normalized = dict(metadata or {})
    normalized.update(extra)
    return normalized


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _strip_html_to_text(content: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(content)
    parser.close()
    return parser.text()


def _load_pdf_from_bytes(pdf_bytes: bytes) -> str:
    try:
        pypdf_module = importlib.import_module("pypdf")
        pdf_reader_type = getattr(pypdf_module, "PdfReader")
    except Exception as exc:
        raise SourceryDependencyError(
            "PDF ingestion requires `pypdf` (install with `uv pip install pypdf`)."
        ) from exc

    reader = pdf_reader_type(BytesIO(pdf_bytes))
    pages = [(page.extract_text() or "") for page in reader.pages]
    text = "\n".join(pages).strip()
    if not text:
        raise SourceryIngestionError("PDF ingestion produced empty text")
    return text


def load_pdf_document(
    path: str | Path,
    *,
    document_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SourceDocument:
    pdf_path = Path(path)
    if not pdf_path.exists():
        raise SourceryIngestionError(f"PDF file does not exist: {pdf_path}")
    text = _load_pdf_from_bytes(pdf_path.read_bytes())
    return SourceDocument(
        document_id=document_id or pdf_path.stem,
        text=text,
        metadata=_normalize_metadata(metadata, source_type="pdf", source=str(pdf_path)),
    )


def load_html_document(
    source: str | Path,
    *,
    document_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    raw_html: bool = False,
) -> SourceDocument:
    if raw_html:
        html_text = str(source)
        doc_id = document_id or "html_document"
        source_ref = "inline_html"
    else:
        html_path = Path(source)
        if not html_path.exists():
            raise SourceryIngestionError(f"HTML file does not exist: {html_path}")
        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
        doc_id = document_id or html_path.stem
        source_ref = str(html_path)

    text = _strip_html_to_text(html_text).strip()
    if not text:
        raise SourceryIngestionError("HTML ingestion produced empty text")
    return SourceDocument(
        document_id=doc_id,
        text=text,
        metadata=_normalize_metadata(metadata, source_type="html", source=source_ref),
    )


def load_url_document(
    url: str,
    *,
    document_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    timeout_seconds: int = 30,
    user_agent: str = "sourcery/0.1",
) -> SourceDocument:
    if not _is_url(url):
        raise SourceryIngestionError(f"Not a valid URL: {url}")

    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read()
        content_type = response.headers.get("Content-Type", "").lower()

    if "application/pdf" in content_type or url.lower().endswith(".pdf"):
        text = _load_pdf_from_bytes(payload)
        source_type = "url_pdf"
    else:
        decoded = payload.decode("utf-8", errors="ignore")
        if "text/html" in content_type or "<html" in decoded.lower():
            text = _strip_html_to_text(decoded)
            source_type = "url_html"
        else:
            text = decoded
            source_type = "url_text"

    stripped = text.strip()
    if not stripped:
        raise SourceryIngestionError("URL ingestion produced empty text")

    return SourceDocument(
        document_id=document_id or f"url:{urlparse(url).netloc}",
        text=stripped,
        metadata=_normalize_metadata(metadata, source_type=source_type, source=url),
    )


def load_ocr_image_document(
    path: str | Path,
    *,
    document_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    language: str = "eng",
) -> SourceDocument:
    image_path = Path(path)
    if not image_path.exists():
        raise SourceryIngestionError(f"Image file does not exist: {image_path}")

    try:
        image_module = importlib.import_module("PIL.Image")
    except Exception as exc:
        raise SourceryDependencyError(
            "OCR image ingestion requires `Pillow` (install with `uv pip install pillow`)."
        ) from exc

    try:
        pytesseract_module = importlib.import_module("pytesseract")
    except Exception as exc:
        raise SourceryDependencyError(
            "OCR image ingestion requires `pytesseract` (install with `uv pip install pytesseract`)."
        ) from exc

    with image_module.open(image_path) as image:
        text = pytesseract_module.image_to_string(image, lang=language)
    stripped = text.strip()
    if not stripped:
        raise SourceryIngestionError("OCR ingestion produced empty text")
    return SourceDocument(
        document_id=document_id or image_path.stem,
        text=stripped,
        metadata=_normalize_metadata(
            metadata,
            source_type="ocr_image",
            source=str(image_path),
            language=language,
        ),
    )


def load_source_document(
    source: SourceDocument | str | Path,
    *,
    document_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SourceDocument:
    if isinstance(source, SourceDocument):
        return source

    source_path = Path(source)
    if source_path.exists():
        suffix = source_path.suffix.lower()
        if suffix == ".pdf":
            return load_pdf_document(source_path, document_id=document_id, metadata=metadata)
        if suffix in _HTML_SUFFIXES:
            return load_html_document(source_path, document_id=document_id, metadata=metadata)
        if suffix in _IMAGE_SUFFIXES:
            return load_ocr_image_document(source_path, document_id=document_id, metadata=metadata)

        text = source_path.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            raise SourceryIngestionError(
                f"Text ingestion produced empty text for file: {source_path}"
            )
        return SourceDocument(
            document_id=document_id or source_path.stem,
            text=text,
            metadata=_normalize_metadata(
                metadata,
                source_type="text_file" if suffix in _TEXT_FILE_SUFFIXES else "file",
                source=str(source_path),
            ),
        )

    if isinstance(source, str) and _is_url(source):
        return load_url_document(source, document_id=document_id, metadata=metadata)

    text = str(source)
    if not text.strip():
        raise SourceryIngestionError("Inline text source is empty")
    return SourceDocument(
        document_id=document_id or "inline_text",
        text=text,
        metadata=_normalize_metadata(metadata, source_type="inline_text", source="inline"),
    )


def load_source_documents(
    sources: Sequence[SourceDocument | str | Path] | SourceDocument | str | Path,
    *,
    metadata: dict[str, Any] | None = None,
) -> list[SourceDocument]:
    if isinstance(sources, (SourceDocument, str, Path)):
        return [load_source_document(sources, metadata=metadata)]

    loaded: list[SourceDocument] = []
    for index, source in enumerate(sources):
        loaded.append(load_source_document(source, document_id=f"doc_{index}", metadata=metadata))
    return loaded
