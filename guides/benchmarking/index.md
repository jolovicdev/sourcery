# Benchmarking

Sourcery provides a benchmark CLI: `sourcery-benchmark`.

This runner currently benchmarks both Sourcery and LangExtract in the same run.

## Prerequisites

```
uv sync --extra benchmark
```

Also set provider credentials.

Default model route (`deepseek/...`):

```
export DEEPSEEK_API_KEY="..."
```

OpenRouter route (`openrouter/...`):

```
export OPENROUTER_API_KEY="..."
```

## Run Benchmark

```
uv run sourcery-benchmark \
  --text-types english,japanese \
  --max-chars 4500 \
  --max-passes 2 \
  --sourcery-model deepseek/deepseek-chat
```

## Important Flags

- `--text-types`: `english,japanese,french,spanish`
- `--max-chars`
- `--max-chunk-chars`
- `--context-window-chars`
- `--max-passes`
- `--batch-concurrency`
- `--temperature`
- `--max-tokens`
- `--retries`
- `--retry-delay-seconds`
- `--sourcery-model`
- `--langextract-model`
- `--deepseek-base-url`
- `--openrouter-base-url`
- `--output-dir`

## Output

A timestamped JSON report in `benchmark_results/` containing:

- benchmark settings,
- tokenization rows,
- framework summaries (`sourcery`, `langextract`),
- per-language records,
- error details for failed runs.

## Notes

- `langextract[openai]` is required for LangExtract benchmark execution.
- Model/provider connection settings are normalized internally from the selected `--sourcery-model` route.
