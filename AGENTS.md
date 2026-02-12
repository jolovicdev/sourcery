## Project Overview
Sourcery is a schema-first extraction framework built on BlackGeorge runtime primitives.

Primary goal:
- extract typed entities/claims from unstructured text and documents,
- ground extractions to source spans,
- provide deterministic post-processing and reviewable output.

Core runtime model:
- Sourcery owns extraction domain logic (chunking, prompts, alignment, merge, reconciliation).
- BlackGeorge owns model execution, flow/workforce orchestration, events, pause/resume, and run storage.

## Tech Stack
- Python 3.12+
- `uv` for environment and dependency management
- Pydantic v2 for contracts
- BlackGeorge for orchestration/runtime
- pytest + ruff + mypy for quality gates
- MkDocs for docs

## Repository Layout
- `sourcery/contracts/` data contracts and public typed models
- `sourcery/pipeline/` chunking, prompt compilation, alignment, merge, validation
- `sourcery/runtime/` engine and BlackGeorge integration
- `sourcery/ingest/` source loaders (text/file/pdf/html/url/ocr)
- `sourcery/io/` JSONL, visualization, reviewer UI
- `sourcery/observability/` trace/event collection
- `sourcery/benchmarks/` Sourcery vs LangExtract benchmark runner
- `tests/` pytest suite
- `docs/` MkDocs pages

## Setup Commands
- Base install: `uv sync`
- Dev tooling: `uv sync --extra dev`
- Ingestion extras: `uv sync --extra ingest`
- Benchmark extras: `uv sync --extra benchmark`
- Docs tooling: `uv sync --extra docs`
- All common extras: `uv sync --extra dev --extra ingest --extra docs --extra benchmark`

## Development Commands
- Run tests: `uv run --extra dev pytest -q`
- Lint: `uv run ruff check .`
- Format (if needed): `uv run ruff format .`
- Type check: `uv run mypy .`
- Serve docs: `uv run mkdocs serve`
- Build docs: `uv run mkdocs build`
- Run benchmark: `uv run sourcery-benchmark --text-types english,japanese,french,spanish --max-chars 4500 --max-passes 2 --sourcery-model deepseek/deepseek-chat`

## Code Style and Conventions
- Keep all public/runtime code fully type-annotated.
- Keep `mypy` strict-clean (`[tool.mypy] strict = true`).
- Keep `ruff` clean; line length is 100.
- Prefer explicit, deterministic logic over implicit behavior.
- Use Pydantic contracts for cross-module boundaries.
- Keep black box boundaries clear:
  - contracts: types only,
  - pipeline: deterministic extraction transforms,
  - runtime: orchestration/provider integration,
  - io/observability: output + telemetry.

## Testing Requirements
- Any behavior change must include or update tests.
- Bug fixes should add a regression test when feasible.
- Keep all existing tests green before finishing.
- Prefer focused unit tests near changed modules plus one integration test when runtime behavior changes.

## Documentation Requirements
- If public API, runtime behavior, or config changes, update docs in `docs/`.
- If you add a new docs page, update `mkdocs.yml` navigation !!!
- Keep `README.md`, `USAGE.md`, and `CODE_EXAMPLES.md` consistent with code behavior.

## Runtime and Safety Notes
- `RuntimeConfig.model` must be set to a valid provider/model route.
- Provider keys must come from environment variables; never hardcode secrets.
- Do not commit `.env` or API keys.
- Do not commit runtime state/databases under `.sourcery/` unless explicitly requested.
- Do not use destructive git commands (`reset --hard`, `checkout --`) unless explicitly asked.

## PR / Commit Checklist
- `uv run ruff check .`
- `uv run mypy .`
- `uv run --extra dev pytest -q`
- Update docs if behavior/API changed
- Keep changes minimal and scoped to the task

## Preferred Commit Style
- Conventional commits:
  - `feat: ...`
  - `fix: ...`
  - `refactor: ...`
  - `docs: ...`
  - `test: ...`
  - `chore: ...`
