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
from sourcery.ingest.vlm_ocr import VLMOCRBackend

_TEXT_FILE_SUFFIXES = {".txt", ".md", ".rst", ".csv", ".json", ".jsonl", ".yaml", ".yml"}
_HTML_SUFFIXES = {".html", ".htm"}


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
    except ModuleNotFoundError as exc:
        if exc.name != "pypdf":
            raise
        raise SourceryDependencyError(
            "PDF ingestion requires the ingest extra. Run `uv sync --extra ingest`."
        ) from exc

    try:
        reader = pypdf_module.PdfReader(BytesIO(pdf_bytes))
        pages = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        raise SourceryIngestionError(f"Could not read PDF: {exc}") from exc
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
    if not pdf_path.is_file():
        raise SourceryIngestionError(f"PDF file does not exist: {pdf_path}")
    try:
        payload = pdf_path.read_bytes()
    except OSError as exc:
        raise SourceryIngestionError(f"Could not read PDF file: {pdf_path}") from exc
    text = _load_pdf_from_bytes(payload)
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
        if not html_path.is_file():
            raise SourceryIngestionError(f"HTML file does not exist: {html_path}")
        try:
            html_text = html_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise SourceryIngestionError(f"Could not read HTML file: {html_path}") from exc
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
    if timeout_seconds <= 0:
        raise SourceryIngestionError("URL timeout must be greater than zero")

    request = Request(url, headers={"User-Agent": user_agent})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read()
            content_type = response.headers.get("Content-Type", "").lower()
            charset = response.headers.get_content_charset() or "utf-8"
    except Exception as exc:
        raise SourceryIngestionError(f"Could not load URL: {url}") from exc

    if "application/pdf" in content_type or urlparse(url).path.lower().endswith(".pdf"):
        text = _load_pdf_from_bytes(payload)
        source_type = "url_pdf"
    else:
        try:
            decoded = payload.decode(charset)
        except (LookupError, UnicodeDecodeError) as exc:
            raise SourceryIngestionError(f"Could not decode URL content as {charset}") from exc
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


def load_source_document(
    source: SourceDocument | str | Path,
    *,
    document_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> SourceDocument:
    if isinstance(source, SourceDocument):
        return source
    if isinstance(source, str) and _is_url(source):
        return load_url_document(source, document_id=document_id, metadata=metadata)

    source_path = Path(source)
    try:
        path_exists = source_path.exists()
    except OSError:
        path_exists = False
    if isinstance(source, Path) and not path_exists:
        raise SourceryIngestionError(f"File does not exist: {source_path}")
    if path_exists:
        if not source_path.is_file():
            raise SourceryIngestionError(f"Source path is not a file: {source_path}")
        suffix = source_path.suffix.lower()
        if suffix == ".pdf":
            return load_pdf_document(source_path, document_id=document_id, metadata=metadata)
        if suffix in _HTML_SUFFIXES:
            return load_html_document(source_path, document_id=document_id, metadata=metadata)

        try:
            text = source_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise SourceryIngestionError(f"Could not read text file: {source_path}") from exc
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


def load_vlm_ocr_document(
    path: str | Path,
    *,
    backend: VLMOCRBackend,
    document_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    prompt: str | None = None,
) -> SourceDocument:
    image_path = Path(path)
    if not image_path.is_file():
        raise SourceryIngestionError(f"Image file does not exist: {image_path}")
    text = backend.extract_text(image_path=image_path, prompt=prompt)
    if not text.strip():
        raise SourceryIngestionError(f"VLM OCR produced empty text for: {image_path}")
    return SourceDocument(
        document_id=document_id or image_path.stem,
        text=text,
        metadata=_normalize_metadata(metadata, source_type="vlm_ocr", source=str(image_path)),
    )


def load_vlm_ocr_documents(
    paths: Sequence[str | Path],
    *,
    backend: VLMOCRBackend,
    metadata: dict[str, Any] | None = None,
    prompt: str | None = None,
) -> list[SourceDocument]:
    loaded: list[SourceDocument] = []
    for index, path in enumerate(paths):
        loaded.append(
            load_vlm_ocr_document(
                path,
                backend=backend,
                document_id=f"ocr_doc_{index}",
                metadata=metadata,
                prompt=prompt,
            )
        )
    return loaded
