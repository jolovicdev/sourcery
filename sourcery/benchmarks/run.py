# Benchmark architecture inspired by langextract (Apache 2.0) - https://github.com/google/langextract

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import importlib
import inspect
import json
import os
from pathlib import Path
import re
import statistics
import time
from typing import Any, Callable

from pydantic import BaseModel

import sourcery
from sourcery.benchmarks.config import TOKENIZATION, TextType
from sourcery.benchmarks.gutenberg import sample_text
from sourcery.contracts import (
    EntitySchemaSet,
    EntitySpec,
    ExtractOptions,
    ExtractRequest,
    ExtractionExample,
    ExtractionTask,
    ExampleExtraction,
    RuntimeConfig,
    SourceDocument,
)


class CharacterAttributes(BaseModel):
    category: str | None = None


@dataclass(slots=True)
class BenchmarkRecord:
    framework: str
    text_type: str
    model: str
    chars: int
    elapsed_seconds: float
    raw_extractions: int
    grounded_extractions: int
    unique_grounded: int
    unresolved_extractions: int
    sample_entities: list[str]
    error: str | None


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed = value.strip().strip('"').strip("'")
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = parsed


def _parse_text_types(raw: str) -> list[TextType]:
    requested = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not requested:
        return [TextType.ENGLISH]
    valid = {item.value: item for item in TextType}
    parsed: list[TextType] = []
    for item in requested:
        if item not in valid:
            valid_values = ", ".join(sorted(valid))
            raise ValueError(f"Unsupported text type '{item}'. Valid values: {valid_values}")
        parsed.append(valid[item])
    return parsed


def _normalize_langextract_model(model: str) -> str:
    if model.startswith("deepseek/") or model.startswith("openrouter/"):
        return model.split("/", 1)[1]
    return model


def _resolve_langextract_connection(
    *,
    sourcery_model: str,
    deepseek_base_url: str | None,
    openrouter_base_url: str | None,
) -> tuple[str, str, str]:
    if sourcery_model.startswith("openrouter/"):
        provider_name = "openrouter"
        key_name = "OPENROUTER_API_KEY"
        api_key = os.environ.get(key_name)
        base_url = (
            openrouter_base_url
            or os.environ.get("OPENROUTER_BASE_URL")
            or "https://openrouter.ai/api/v1"
        )
    else:
        provider_name = "deepseek"
        key_name = "DEEPSEEK_API_KEY"
        api_key = os.environ.get(key_name)
        base_url = (
            deepseek_base_url or os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
        )
    if not api_key:
        raise RuntimeError(f"{key_name} is not set. Put it in .env or export it.")
    return provider_name, api_key, base_url


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\\w+|[^\\w\\s]", text, flags=re.UNICODE)


def _benchmark_tokenization() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for word_count in TOKENIZATION.sizes:
        text = " ".join(["word"] * word_count)
        _ = _tokenize(text)

        timings: list[float] = []
        for _ in range(TOKENIZATION.iterations):
            started = time.perf_counter()
            tokenized = _tokenize(text)
            timings.append(time.perf_counter() - started)

        avg_seconds = statistics.mean(timings)
        rows.append(
            {
                "words": word_count,
                "tokens": len(tokenized),
                "avg_ms": round(avg_seconds * 1000, 3),
                "tokens_per_sec": round(len(tokenized) / avg_seconds, 3),
            }
        )
    return rows


def _build_sourcery_task() -> ExtractionTask:
    return ExtractionTask(
        instructions="Extract character names from the text. Return only exact text spans from the source.",
        schema=EntitySchemaSet(
            entities=[
                EntitySpec(name="character", attributes_model=CharacterAttributes),
            ]
        ),
        examples=[
            ExtractionExample(
                text="Macbeth speaks to Lady Macbeth about Duncan.",
                extractions=[
                    ExampleExtraction(
                        entity="character", text="Macbeth", attributes={"category": "person"}
                    ),
                    ExampleExtraction(
                        entity="character", text="Lady Macbeth", attributes={"category": "person"}
                    ),
                    ExampleExtraction(
                        entity="character", text="Duncan", attributes={"category": "person"}
                    ),
                ],
            )
        ],
        strict_example_alignment=True,
    )


def _retry_call(
    *,
    retries: int,
    initial_delay: float,
    operation: Callable[[], BenchmarkRecord],
) -> BenchmarkRecord:
    attempts = max(retries, 1)
    delay = max(initial_delay, 0.0)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            time.sleep(delay)
            delay = delay * 1.5 if delay > 0 else 0.0
    if last_error is None:
        raise RuntimeError("retry loop finished without result or error")
    raise last_error


def _run_sourcery(
    *,
    text_type: TextType,
    text: str,
    model: str,
    max_chunk_chars: int,
    context_window_chars: int,
    max_passes: int,
    batch_concurrency: int,
    temperature: float,
    max_tokens: int | None,
) -> BenchmarkRecord:
    started = time.perf_counter()
    request = ExtractRequest(
        documents=[
            SourceDocument(
                document_id=f"{text_type.value}_doc",
                text=text,
                metadata={"text_type": text_type.value},
            )
        ],
        task=_build_sourcery_task(),
        options=ExtractOptions(
            max_chunk_chars=max_chunk_chars,
            context_window_chars=context_window_chars,
            max_passes=max_passes,
            batch_concurrency=batch_concurrency,
            enable_fuzzy_alignment=True,
            fuzzy_alignment_threshold=0.82,
            accept_partial_exact=False,
            stop_when_no_new_extractions=True,
            allow_unresolved=False,
        ),
        runtime=RuntimeConfig(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            storage_dir=".sourcery",
            respect_context_window=True,
        ),
    )
    result = sourcery.extract(request)
    elapsed = time.perf_counter() - started
    doc = result.documents[0]
    status_counts = Counter(item.alignment_status for item in doc.extractions)
    grounded = [item for item in doc.extractions if item.alignment_status != "unresolved"]
    unique_grounded = sorted({item.text for item in grounded})
    return BenchmarkRecord(
        framework="sourcery",
        text_type=text_type.value,
        model=model,
        chars=len(text),
        elapsed_seconds=elapsed,
        raw_extractions=len(doc.extractions),
        grounded_extractions=len(grounded),
        unique_grounded=len(unique_grounded),
        unresolved_extractions=status_counts.get("unresolved", 0),
        sample_entities=unique_grounded[:10],
        error=None,
    )


def _build_langextract_example(langextract_data: Any) -> Any:
    return langextract_data.ExampleData(
        text="Macbeth speaks to Lady Macbeth about Duncan.",
        extractions=[
            langextract_data.Extraction(extraction_text="Macbeth", extraction_class="Character"),
            langextract_data.Extraction(
                extraction_text="Lady Macbeth", extraction_class="Character"
            ),
            langextract_data.Extraction(extraction_text="Duncan", extraction_class="Character"),
        ],
    )


def _filter_supported_kwargs(target: Callable[..., Any], values: dict[str, Any]) -> dict[str, Any]:
    parameters = inspect.signature(target).parameters
    if any(item.kind is inspect.Parameter.VAR_KEYWORD for item in parameters.values()):
        return dict(values)
    return {key: value for key, value in values.items() if key in parameters}


def _call_langextract_extract(extractor: Callable[..., Any], values: dict[str, Any]) -> Any:
    active_kwargs = _filter_supported_kwargs(extractor, values)
    while True:
        try:
            return extractor(**active_kwargs)
        except TypeError as exc:
            message = str(exc)
            marker = "unexpected keyword argument '"
            if marker not in message:
                raise
            key = message.split(marker, 1)[1].split("'", 1)[0]
            if key not in active_kwargs:
                raise
            active_kwargs.pop(key)


def _run_langextract(
    *,
    text_type: TextType,
    text: str,
    model: str,
    api_key: str,
    base_url: str,
    batch_concurrency: int,
    max_chunk_chars: int,
    max_passes: int,
    context_window_chars: int,
    temperature: float,
) -> BenchmarkRecord:
    langextract = importlib.import_module("langextract")
    langextract_data = importlib.import_module("langextract.data")
    langextract_factory = importlib.import_module("langextract.factory")
    langextract_providers = importlib.import_module("langextract.providers")

    started = time.perf_counter()
    langextract_providers.load_builtins_once()
    langextract_providers.load_plugins_once()
    config = langextract_factory.ModelConfig(
        model_id=model,
        provider="openai",
        provider_kwargs={
            "api_key": api_key,
            "base_url": base_url,
            "temperature": temperature,
            "max_workers": batch_concurrency,
        },
    )
    raw_kwargs: dict[str, Any] = {
        "text_or_documents": text,
        "prompt_description": "Extract character names from this text",
        "examples": [_build_langextract_example(langextract_data)],
        "config": config,
        "batch_length": max(batch_concurrency, 1),
        "max_workers": batch_concurrency,
        "extraction_passes": max_passes,
        "context_window_chars": context_window_chars,
        "max_char_buffer": max_chunk_chars,
        "show_progress": False,
    }
    extraction = _call_langextract_extract(langextract.extract, raw_kwargs)
    elapsed = time.perf_counter() - started
    docs = extraction if isinstance(extraction, list) else [extraction]
    entities: list[str] = []
    grounded = 0
    for doc in docs:
        for item in doc.extractions:
            if not item.extraction_text:
                continue
            entities.append(item.extraction_text)
            interval = item.char_interval
            if interval and interval.start_pos is not None and interval.end_pos is not None:
                grounded += 1
    unique_grounded = sorted(set(entities))
    unresolved = max(len(entities) - grounded, 0)
    return BenchmarkRecord(
        framework="langextract",
        text_type=text_type.value,
        model=model,
        chars=len(text),
        elapsed_seconds=elapsed,
        raw_extractions=len(entities),
        grounded_extractions=grounded,
        unique_grounded=len(unique_grounded),
        unresolved_extractions=unresolved,
        sample_entities=unique_grounded[:10],
        error=None,
    )


def _record_error(
    *,
    framework: str,
    text_type: TextType,
    model: str,
    text: str,
    error: Exception,
) -> BenchmarkRecord:
    return BenchmarkRecord(
        framework=framework,
        text_type=text_type.value,
        model=model,
        chars=len(text),
        elapsed_seconds=0.0,
        raw_extractions=0,
        grounded_extractions=0,
        unique_grounded=0,
        unresolved_extractions=0,
        sample_entities=[],
        error=f"{type(error).__name__}: {error}",
    )


def _framework_summary(records: list[BenchmarkRecord], framework: str) -> dict[str, Any]:
    subset = [item for item in records if item.framework == framework]
    success = [item for item in subset if item.error is None]
    if not success:
        return {
            "runs": len(subset),
            "successes": 0,
            "avg_elapsed_seconds": None,
            "avg_grounded_extractions": None,
            "avg_unique_grounded": None,
            "total_grounded_extractions": 0,
            "total_unique_grounded": 0,
        }
    return {
        "runs": len(subset),
        "successes": len(success),
        "avg_elapsed_seconds": round(statistics.mean(item.elapsed_seconds for item in success), 3),
        "avg_grounded_extractions": round(
            statistics.mean(item.grounded_extractions for item in success), 3
        ),
        "avg_unique_grounded": round(statistics.mean(item.unique_grounded for item in success), 3),
        "total_grounded_extractions": sum(item.grounded_extractions for item in success),
        "total_unique_grounded": sum(item.unique_grounded for item in success),
    }


def _print_row(record: BenchmarkRecord) -> None:
    status = "ok" if record.error is None else "error"
    print(
        f"{record.text_type:<10} {record.framework:<11} {record.elapsed_seconds:>8.2f}s "
        f"grounded={record.grounded_extractions:>4} unique={record.unique_grounded:>4} {status}"
    )
    if record.error is not None:
        print(f"  -> {record.error}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Temporary Sourcery vs LangExtract benchmark")
    parser.add_argument(
        "--text-types",
        default="english",
        help="Comma-separated set: english,japanese,french,spanish",
    )
    parser.add_argument("--max-chars", type=int, default=2500)
    parser.add_argument("--max-chunk-chars", type=int, default=1200)
    parser.add_argument("--context-window-chars", type=int, default=200)
    parser.add_argument("--max-passes", type=int, default=1)
    parser.add_argument("--batch-concurrency", type=int, default=4)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=700)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-delay-seconds", type=float, default=2.0)
    parser.add_argument("--sourcery-model", default="deepseek/deepseek-chat")
    parser.add_argument("--langextract-model", default=None)
    parser.add_argument("--deepseek-base-url", default=None)
    parser.add_argument("--openrouter-base-url", default=None)
    parser.add_argument("--output-dir", default="benchmark_results")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> Path:
    _load_dotenv()
    text_types = _parse_text_types(args.text_types)
    sourcery_model = args.sourcery_model
    langextract_model = _normalize_langextract_model(args.langextract_model or sourcery_model)
    provider_name, api_key, provider_base_url = _resolve_langextract_connection(
        sourcery_model=sourcery_model,
        deepseek_base_url=args.deepseek_base_url,
        openrouter_base_url=args.openrouter_base_url,
    )

    tokenization = _benchmark_tokenization()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    records: list[BenchmarkRecord] = []

    print("=" * 72)
    print("SOURCERY VS LANGEXTRACT TEMP BENCHMARK")
    print("=" * 72)
    print(f"sourcery_model={sourcery_model}")
    print(f"langextract_model={langextract_model}")
    print(f"text_types={','.join(item.value for item in text_types)}")
    print(f"provider={provider_name}")
    print(f"provider_base_url={provider_base_url}")
    print("-" * 72)

    for row in tokenization:
        print(
            f"tokenization words={row['words']:>6} tokens={row['tokens']:>7} "
            f"avg_ms={row['avg_ms']:>8} tok_per_sec={row['tokens_per_sec']:>12}"
        )
    print("-" * 72)

    for text_type in text_types:
        text = sample_text(text_type, max_chars=args.max_chars)

        try:
            sourcery_record = _retry_call(
                retries=args.retries,
                initial_delay=args.retry_delay_seconds,
                operation=lambda: _run_sourcery(
                    text_type=text_type,
                    text=text,
                    model=sourcery_model,
                    max_chunk_chars=args.max_chunk_chars,
                    context_window_chars=args.context_window_chars,
                    max_passes=args.max_passes,
                    batch_concurrency=args.batch_concurrency,
                    temperature=args.temperature,
                    max_tokens=args.max_tokens,
                ),
            )
        except Exception as exc:
            sourcery_record = _record_error(
                framework="sourcery",
                text_type=text_type,
                model=sourcery_model,
                text=text,
                error=exc,
            )
        records.append(sourcery_record)
        _print_row(sourcery_record)

        try:
            langextract_record = _retry_call(
                retries=args.retries,
                initial_delay=args.retry_delay_seconds,
                operation=lambda: _run_langextract(
                    text_type=text_type,
                    text=text,
                    model=langextract_model,
                    api_key=api_key,
                    base_url=provider_base_url,
                    batch_concurrency=args.batch_concurrency,
                    max_chunk_chars=args.max_chunk_chars,
                    max_passes=args.max_passes,
                    context_window_chars=args.context_window_chars,
                    temperature=args.temperature,
                ),
            )
        except Exception as exc:
            langextract_record = _record_error(
                framework="langextract",
                text_type=text_type,
                model=langextract_model,
                text=text,
                error=exc,
            )
        records.append(langextract_record)
        _print_row(langextract_record)
        print("-" * 72)

    sourcery_summary = _framework_summary(records, "sourcery")
    langextract_summary = _framework_summary(records, "langextract")

    comparison: dict[str, Any] = {
        "timestamp_utc": timestamp,
        "settings": {
            "text_types": [item.value for item in text_types],
            "max_chars": args.max_chars,
            "max_chunk_chars": args.max_chunk_chars,
            "context_window_chars": args.context_window_chars,
            "max_passes": args.max_passes,
            "batch_concurrency": args.batch_concurrency,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "retries": args.retries,
            "retry_delay_seconds": args.retry_delay_seconds,
            "sourcery_model": sourcery_model,
            "langextract_model": langextract_model,
            "provider": provider_name,
            "provider_base_url": provider_base_url,
        },
        "tokenization": tokenization,
        "summary": {
            "sourcery": sourcery_summary,
            "langextract": langextract_summary,
        },
        "records": [asdict(item) for item in records],
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"sourcery_vs_langextract_{timestamp}.json"
    output_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")

    print("SUMMARY")
    print(f"sourcery={sourcery_summary}")
    print(f"langextract={langextract_summary}")
    print(f"output={output_path}")
    return output_path


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        run(args)
        return 0
    except Exception as exc:
        print(f"benchmark failed: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
