from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from sourcery.benchmarks.config import TextType
from sourcery.benchmarks.gutenberg import extract_main_content
from sourcery.benchmarks.run import (
    _call_langextract_extract,
    _filter_supported_kwargs,
    _normalize_langextract_model,
    _parse_text_types,
    _resolve_langextract_connection,
    _run_langextract,
    parse_args,
)


def test_parse_text_types_accepts_multiple_values() -> None:
    parsed = _parse_text_types("english,japanese")
    assert parsed == [TextType.ENGLISH, TextType.JAPANESE]


def test_benchmark_defaults_to_deepseek_v4_flash() -> None:
    assert parse_args([]).sourcery_model == "deepseek/deepseek-v4-flash"


def test_parse_text_types_rejects_invalid_value() -> None:
    try:
        _parse_text_types("english,invalid")
    except ValueError as exc:
        assert "Unsupported text type" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_extract_main_content_prefers_gutenberg_markers() -> None:
    full_text = (
        "header\n*** START OF TEST BOOK ***\nline one\nline two\n*** END OF TEST BOOK ***\nfooter\n"
    )
    assert extract_main_content(full_text) == "line one\nline two"


def test_filter_supported_kwargs_removes_unknown_fields() -> None:
    def target(a: int, b: int) -> int:
        return a + b

    filtered = _filter_supported_kwargs(target, {"a": 1, "b": 2, "c": 3})
    assert filtered == {"a": 1, "b": 2}


def test_filter_supported_kwargs_keeps_values_for_var_kwargs_wrapper() -> None:
    def wrapper(**kwargs: int) -> int:
        return kwargs["a"] + kwargs["b"]

    filtered = _filter_supported_kwargs(wrapper, {"a": 1, "b": 2, "c": 3})
    assert filtered == {"a": 1, "b": 2, "c": 3}


def test_call_langextract_extract_drops_unknown_kwargs_iteratively() -> None:
    def target(a: int, b: int = 0) -> int:
        return a + b

    def wrapper(**kwargs: int) -> int:
        return target(**kwargs)

    result = _call_langextract_extract(wrapper, {"a": 2, "b": 3, "c": 9})
    assert result == 5


def test_normalize_langextract_model_strips_provider_prefixes() -> None:
    assert _normalize_langextract_model("deepseek/deepseek-v4-flash") == "deepseek-v4-flash"
    assert (
        _normalize_langextract_model("openrouter/google/gemini-3-flash-preview")
        == "google/gemini-3-flash-preview"
    )
    assert _normalize_langextract_model("gpt-4o-mini") == "gpt-4o-mini"


def test_resolve_langextract_connection_uses_openrouter_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    provider_name, api_key, base_url = _resolve_langextract_connection(
        sourcery_model="openrouter/google/gemini-3-flash-preview",
        deepseek_base_url=None,
        openrouter_base_url=None,
    )
    assert provider_name == "openrouter"
    assert api_key == "test-key"
    assert base_url == "https://openrouter.ai/api/v1"


def test_resolve_langextract_connection_uses_deepseek_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    provider_name, api_key, base_url = _resolve_langextract_connection(
        sourcery_model="deepseek/deepseek-v4-flash",
        deepseek_base_url=None,
        openrouter_base_url=None,
    )
    assert provider_name == "deepseek"
    assert api_key == "test-key"
    assert base_url == "https://api.deepseek.com"


def test_langextract_unique_grounded_excludes_unresolved_entities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = SimpleNamespace(
        extractions=[
            SimpleNamespace(
                extraction_text="Alice",
                char_interval=SimpleNamespace(start_pos=0, end_pos=5),
            ),
            SimpleNamespace(extraction_text="Ghost", char_interval=None),
        ]
    )
    modules = {
        "langextract": SimpleNamespace(extract=lambda **_kwargs: document),
        "langextract.data": SimpleNamespace(
            ExampleData=lambda **kwargs: kwargs,
            Extraction=lambda **kwargs: kwargs,
        ),
        "langextract.factory": SimpleNamespace(ModelConfig=lambda **kwargs: kwargs),
        "langextract.providers": SimpleNamespace(
            load_builtins_once=lambda: None,
            load_plugins_once=lambda: None,
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    record = _run_langextract(
        text_type=TextType.ENGLISH,
        text="Alice and Ghost",
        model="deepseek-v4-flash",
        api_key="test-key",
        base_url="https://example.test",
        batch_concurrency=2,
        max_chunk_chars=100,
        max_passes=1,
        context_window_chars=20,
        temperature=0.0,
    )

    assert record.raw_extractions == 2
    assert record.grounded_extractions == 1
    assert record.unique_grounded == 1
    assert record.unresolved_extractions == 1
    assert record.sample_entities == ["Alice"]
