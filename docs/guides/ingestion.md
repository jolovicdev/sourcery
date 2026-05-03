# Load Text, PDFs, URLs, HTML, and Images into Sourcery

Ingestion normalizes heterogeneous inputs into `SourceDocument`.
Implementation lives in `sourcery/ingest/loaders.py`.

## Supported Source Types

- Inline text
- Local text-like files: `.txt`, `.md`, `.rst`, `.csv`, `.json`, `.jsonl`, `.yaml`, `.yml`
- PDF files (`.pdf`, requires `pypdf`)
- HTML files and raw HTML
- HTTP/HTTPS URLs

## Primary APIs

- `load_source_document(source, ...)`
- `load_source_documents(sources, ...)`

Extended APIs:

- `load_pdf_document(path, ...)`
- `load_html_document(source, raw_html=False, ...)`
- `load_url_document(url, ...)`
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
- Missing PDF/HTML path in dedicated loaders -> `SourceryIngestionError`

## VLM OCR

Image-based text extraction via any vision-language model. Sourcery provides the interface; the model does the work. No OCR-specific dependencies required.

### Interface

`VLMOCRBackend` is a protocol — implement `extract_text(*, image_path, prompt) -> str` and it works. Sourcery ships `BlackGeorgeVLMOCRBackend` which delegates to blackgeorge's multimodal worker. Swap the `runtime.model` to use any VLM your provider supports.

### Examples

```python
from sourcery.contracts import RuntimeConfig
from sourcery.ingest import BlackGeorgeVLMOCRBackend, load_vlm_ocr_document

backend = BlackGeorgeVLMOCRBackend(
    RuntimeConfig(model="gemini/gemini-2.5-flash", temperature=0.0),
)

doc = load_vlm_ocr_document("scan.png", backend=backend)
```

With a custom prompt for structured extraction:

```python
doc = load_vlm_ocr_document(
    "invoice.jpg",
    backend=backend,
    prompt="Extract invoice number, date, total amount, and line items as a table.",
)
```

Batch processing:

```python
from sourcery.ingest import load_vlm_ocr_documents

docs = load_vlm_ocr_documents(
    ["page1.png", "page2.png", "page3.png"],
    backend=backend,
)
```

Custom backend for any VLM:

```python
from sourcery.ingest import VLMOCRBackend

class MyVLMBackend:
    def extract_text(self, *, image_path, prompt=None):
        # call your model here
        return extracted_text

assert isinstance(MyVLMBackend(), VLMOCRBackend)  # True
doc = load_vlm_ocr_document("scan.png", backend=MyVLMBackend())
```

## Operational Notes

- URL ingestion auto-detects PDF vs HTML vs plain text by content type and payload.
- `load_source_document("missing/path.txt")` does not raise by default; because the path does not exist, it is treated as inline text. Use dedicated loaders when you require strict path existence checks.
- VLM OCR loaders raise `SourceryIngestionError` on missing files or empty model output.
