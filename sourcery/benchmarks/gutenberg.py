# Benchmark architecture inspired by langextract (Apache 2.0) - https://github.com/google/langextract

from __future__ import annotations

import urllib.error
import urllib.request
from typing import cast

from sourcery.benchmarks.config import GUTENBERG_TEXTS, TextType


def download_text(url: str) -> str:
    try:
        with urllib.request.urlopen(url) as response:
            payload = cast(bytes, response.read())
            return payload.decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise RuntimeError(f"Could not download from {url}: {exc}") from exc


def extract_main_content(full_text: str) -> str:
    start_marker = "*** START OF"
    end_marker = "*** END OF"
    upper = full_text.upper()
    start_index = upper.find(start_marker)
    end_index = upper.find(end_marker)
    if start_index != -1 and end_index != -1:
        content_start = full_text.find("\n", start_index) + 1
        line_end = full_text.find("***", start_index + 3)
        if line_end != -1 and line_end < content_start + 100:
            content_start = full_text.find("\n", line_end) + 1
        return full_text[content_start:end_index].strip()
    text_length = len(full_text)
    return full_text[int(text_length * 0.2) : int(text_length * 0.8)].strip()


def sample_text(text_type: TextType, *, max_chars: int) -> str:
    downloaded = download_text(GUTENBERG_TEXTS[text_type])
    content = extract_main_content(downloaded)
    mid_point = len(content) // 2
    start_chunk = max(0, mid_point - 2500)
    text = content[start_chunk : start_chunk + 5000].strip()
    return text[:max_chars] if max_chars > 0 else text
