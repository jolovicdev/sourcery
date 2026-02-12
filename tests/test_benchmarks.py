from __future__ import annotations

import pytest

from sourcery.benchmarks.config import TextType
from sourcery.benchmarks.gutenberg import extract_main_content
from sourcery.benchmarks.run import (
    _call_langextract_extract,
    _filter_supported_kwargs,
    _normalize_langextract_model,
    _parse_text_types,
    _resolve_langextract_connection,
)


def test_parse_text_types_accepts_multiple_values() -> None:
    parsed = _parse_text_types("english,japanese")
    assert parsed == [TextType.ENGLISH, TextType.JAPANESE]


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
    assert _normalize_langextract_model("deepseek/deepseek-chat") == "deepseek-chat"
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
        sourcery_model="deepseek/deepseek-chat",
        deepseek_base_url=None,
        openrouter_base_url=None,
    )
    assert provider_name == "deepseek"
    assert api_key == "test-key"
    assert base_url == "https://api.deepseek.com"
