from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import re

from sourcery.contracts import SourceDocument, TextChunk

_TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True, slots=True)
class TokenSpan:
    token: str
    char_start: int
    char_end: int


def tokenize_with_spans(text: str) -> list[TokenSpan]:
    return [
        TokenSpan(token=match.group(0), char_start=match.start(), char_end=match.end())
        for match in _TOKEN_RE.finditer(text)
    ]


def _build_sentence_ranges(text: str) -> list[tuple[int, int]]:
    if not text:
        return []
    ranges: list[tuple[int, int]] = []
    last = 0
    for match in _SENTENCE_BOUNDARY_RE.finditer(text):
        end = match.start()
        if end > last:
            ranges.append((last, end))
        last = match.end()
    if last < len(text):
        ranges.append((last, len(text)))
    if not ranges:
        ranges.append((0, len(text)))
    return ranges


def _coalesce_by_char_limit(
    text: str,
    sentence_ranges: list[tuple[int, int]],
    max_chunk_chars: int,
) -> list[tuple[int, int]]:
    chunks: list[tuple[int, int]] = []
    current_start: int | None = None
    current_end: int | None = None

    def flush_current() -> None:
        nonlocal current_start, current_end
        if current_start is None or current_end is None:
            return
        if current_end > current_start:
            chunks.append((current_start, current_end))
        current_start = None
        current_end = None

    for start, end in sentence_ranges:
        if end - start > max_chunk_chars:
            flush_current()
            chunk_start = start
            while chunk_start < end:
                chunk_end = min(chunk_start + max_chunk_chars, end)
                while (
                    chunk_end < end and text[chunk_end - 1].isalnum() and text[chunk_end].isalnum()
                ):
                    chunk_end -= 1
                    if chunk_end <= chunk_start:
                        chunk_end = min(chunk_start + max_chunk_chars, end)
                        break
                chunks.append((chunk_start, chunk_end))
                chunk_start = chunk_end
            continue

        if current_start is None:
            current_start = start
            current_end = end
            continue

        proposed_end = end
        if proposed_end - current_start <= max_chunk_chars:
            current_end = proposed_end
            continue

        flush_current()
        current_start = start
        current_end = end

    flush_current()
    return [(start, end) for start, end in chunks if start < end]


def _token_bounds_for_char_range(
    tokens: list[TokenSpan], char_start: int, char_end: int
) -> tuple[int | None, int | None]:
    if not tokens:
        return None, None
    token_start: int | None = None
    token_end: int | None = None
    for index, token in enumerate(tokens):
        if token.char_end <= char_start:
            continue
        if token.char_start >= char_end:
            break
        if token_start is None:
            token_start = index
        token_end = index + 1
    return token_start, token_end


def plan_chunks(
    documents: Iterable[SourceDocument],
    *,
    pass_id: int,
    max_chunk_chars: int,
    context_window_chars: int,
) -> list[TextChunk]:
    chunks: list[TextChunk] = []
    for document in documents:
        text = document.text
        sentence_ranges = _build_sentence_ranges(text)
        char_ranges = _coalesce_by_char_limit(text, sentence_ranges, max_chunk_chars)
        tokens = tokenize_with_spans(text)
        previous_text = ""
        for order_index, (char_start, char_end) in enumerate(char_ranges):
            token_start, token_end = _token_bounds_for_char_range(tokens, char_start, char_end)
            previous_context = None
            if context_window_chars > 0 and previous_text:
                previous_context = previous_text[-context_window_chars:]
            chunk = TextChunk(
                chunk_id=f"{document.document_id}:p{pass_id}:c{order_index}",
                document_id=document.document_id,
                pass_id=pass_id,
                order_index=order_index,
                text=text[char_start:char_end],
                char_start=char_start,
                char_end=char_end,
                token_start=token_start,
                token_end=token_end,
                previous_context=previous_context,
            )
            chunks.append(chunk)
            previous_text = chunk.text
    return chunks
