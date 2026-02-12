# Ingestion

Ingestion normalizes heterogeneous inputs into `SourceDocument`.
Implementation lives in `sourcery/ingest/loaders.py`.

## Supported Source Types

- Inline text
- Local text-like files: `.txt`, `.md`, `.rst`, `.csv`, `.json`, `.jsonl`, `.yaml`, `.yml`
- PDF files (`.pdf`, requires `pypdf`)
- HTML files and raw HTML
- HTTP/HTTPS URLs
- OCR image files: `.png`, `.jpg`, `.jpeg`, `.webp`, `.tiff`, `.bmp` (requires `Pillow` + `pytesseract`)

## Primary APIs

- `load_source_document(source, ...)`
- `load_source_documents(sources, ...)`

Extended APIs:

- `load_pdf_document(path, ...)`
- `load_html_document(source, raw_html=False, ...)`
- `load_url_document(url, ...)`
- `load_ocr_image_document(path, ...)`

## Examples

Load one source automatically:

```python
from sourcery.ingest import load_source_document

doc = load_source_document("reports/q4.pdf")
```

Load multiple mixed sources:

```python
from sourcery.ingest import load_source_documents

documents = load_source_documents([
    "notes.txt",
    "https://example.com/post",
    "Raw inline text to extract from",
])
```

Load raw HTML string explicitly:

```python
from sourcery.ingest.loaders import load_html_document

doc = load_html_document("<html><body><h1>Hello</h1></body></html>", raw_html=True)
```

## Failure Modes

- Missing optional dependency -> `SourceryDependencyError`
- Empty parsed content -> `SourceryIngestionError`
- Invalid URL passed to `load_url_document(...)` -> `SourceryIngestionError`
- Missing PDF/HTML/image path in dedicated loaders -> `SourceryIngestionError`

## Operational Notes

- URL ingestion auto-detects PDF vs HTML vs plain text by content type and payload.
- OCR requires system Tesseract to be installed in addition to Python packages.
- `load_source_document("missing/path.txt")` does not raise by default; because the path does not exist, it is treated as inline text. Use dedicated loaders when you require strict path existence checks.
