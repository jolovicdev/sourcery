# Testing And Validation

Run the full validation suite before merging changes.

## Full Suite

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check sourcery tests
uv run --extra dev mypy sourcery
```

## Focused Test Runs

```bash
uv run --extra dev pytest -q tests/test_engine.py
uv run --extra dev pytest -q tests/test_ingest.py
uv run --extra dev pytest -q tests/test_blackgeorge_runtime.py
```

## What Current Tests Cover

- contract validation and boundary checks,
- deterministic chunking/alignment/merge behavior,
- runtime error classification and retry behavior,
- BlackGeorge runtime refinement/reconciliation ordering,
- API helpers and ingestion behavior,
- JSONL + HTML output correctness,
- benchmark utility behavior.

## Recommended Regression Pattern

When fixing a bug:

1. Add a failing test that reproduces the issue.
2. Fix the implementation.
3. Run focused tests, then the full suite.
