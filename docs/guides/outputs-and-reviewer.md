# Outputs And Reviewer

Sourcery supports machine-friendly persistence and human review workflows.

## JSONL Persistence

Write extraction output:

```python
from sourcery.io import save_extract_result_jsonl

save_extract_result_jsonl(result, "output/result.jsonl")
```

Load documents back:

```python
from sourcery.io import load_document_results_jsonl

documents = load_document_results_jsonl("output/result.jsonl")
```

Iterate rows directly:

```python
from sourcery.io import iter_document_rows

for row in iter_document_rows("output/result.jsonl"):
    print(row["document_id"], len(row["extractions"]))
```

## Viewer HTML

Generate read-only visualization with highlighted grounded spans:

```python
from sourcery.io import write_document_html

write_document_html(result.documents[0], "output/document.viewer.html")
```

Notebook/inline rendering helper:

```python
from sourcery.io import visualize

html_or_display = visualize(result.documents[0])
```

`visualize("path/to/result.jsonl")` is also supported and uses the first document in the file.

## Reviewer HTML

Generate interactive review UI from a `DocumentResult`:

```python
from sourcery.io import write_reviewer_html

write_reviewer_html(result.documents[0], "output/document.reviewer.html")
```

Generate reviewer directly from JSONL:

```python
from sourcery.io import write_reviewer_html

write_reviewer_html("output/result.jsonl", "output/document.reviewer.html")
```

When a JSONL path is provided, the reviewer uses the first document row.

Reviewer capabilities:

- search by text/attributes,
- filter by entity and review status,
- approve/reject/reset per extraction or filtered set,
- export approved rows to JSONL and CSV,
- persist review state in browser local storage.
