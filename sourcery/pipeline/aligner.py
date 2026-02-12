from __future__ import annotations

from collections.abc import Iterable
from difflib import SequenceMatcher
import re
from typing import Any

from pydantic import BaseModel

from sourcery.contracts import (
    AlignedExtraction,
    AlignmentStatus,
    EntitySchemaSet,
    ExtractOptions,
    ExtractionCandidate,
    ExtractionProvenance,
    TextChunk,
)
from sourcery.pipeline.chunking import TokenSpan, tokenize_with_spans


class AlignmentResult(BaseModel):
    aligned: list[AlignedExtraction]
    unresolved_count: int = 0
    warnings: list[str] = []


def _find_exact_span(text: str, query: str) -> tuple[int, int] | None:
    pattern = re.escape(query)
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match is None:
        return None
    return match.start(), match.end()


def _normalize_token(token: str) -> str:
    normalized = token.lower()
    if len(normalized) > 3 and normalized.endswith("s") and not normalized.endswith("ss"):
        normalized = normalized[:-1]
    return normalized


def _fuzzy_span(text: str, query: str, threshold: float) -> tuple[int, int] | None:
    text_tokens = tokenize_with_spans(text)
    query_tokens = tokenize_with_spans(query)
    if not text_tokens or not query_tokens:
        return None

    normalized_query = [_normalize_token(token.token) for token in query_tokens]
    matcher = SequenceMatcher(autojunk=False)
    best_ratio = 0.0
    best_window: tuple[int, int] | None = None

    for start_idx in range(len(text_tokens)):
        max_window = min(len(text_tokens), start_idx + max(1, len(query_tokens) * 2))
        for end_idx in range(start_idx + 1, max_window + 1):
            window_tokens = [
                _normalize_token(token.token) for token in text_tokens[start_idx:end_idx]
            ]
            matcher.set_seqs(window_tokens, normalized_query)
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_window = (start_idx, end_idx)

    if best_window is None or best_ratio < threshold:
        return None

    start_token = text_tokens[best_window[0]]
    end_token = text_tokens[best_window[1] - 1]
    return start_token.char_start, end_token.char_end


def _partial_span(text: str, query: str) -> tuple[int, int] | None:
    query_tokens = tokenize_with_spans(query)
    if len(query_tokens) < 2:
        return None
    for token in query_tokens:
        pattern = re.escape(token.token)
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match is not None:
            return match.start(), match.end()
    return None


def _token_range(
    tokens: list[TokenSpan], char_start: int, char_end: int
) -> tuple[int | None, int | None]:
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


def _coerce_attributes(
    candidate: ExtractionCandidate, schema: EntitySchemaSet
) -> tuple[BaseModel | dict[str, Any], str | None]:
    by_name = schema.by_name()
    entity_spec = by_name.get(candidate.entity)
    if entity_spec is None:
        return candidate.attributes, f"Unknown entity '{candidate.entity}' from model output"

    if isinstance(candidate.attributes, BaseModel):
        return candidate.attributes, None

    try:
        validated = entity_spec.attributes_model.model_validate(candidate.attributes)
        return validated, None
    except Exception as exc:
        return candidate.attributes, f"Invalid attributes for entity '{candidate.entity}': {exc}"


def align_candidates(
    *,
    candidates: Iterable[ExtractionCandidate],
    chunk: TextChunk,
    schema: EntitySchemaSet,
    options: ExtractOptions,
    provenance_base: ExtractionProvenance,
) -> AlignmentResult:
    aligned: list[AlignedExtraction] = []
    warnings: list[str] = []
    unresolved_count = 0

    chunk_tokens = tokenize_with_spans(chunk.text)

    for candidate in candidates:
        attributes, attributes_warning = _coerce_attributes(candidate, schema)
        if attributes_warning is not None:
            warnings.append(attributes_warning)

        status: AlignmentStatus = "unresolved"
        span = _find_exact_span(chunk.text, candidate.text)
        if span is not None:
            status = "exact"
        elif options.enable_fuzzy_alignment:
            span = _fuzzy_span(chunk.text, candidate.text, options.fuzzy_alignment_threshold)
            if span is not None:
                status = "fuzzy"

        if span is None and options.accept_partial_exact:
            span = _partial_span(chunk.text, candidate.text)
            if span is not None:
                status = "partial"

        if span is None:
            unresolved_count += 1
            if not options.allow_unresolved:
                continue
            span = (0, 0)

        local_char_start, local_char_end = span
        global_char_start = chunk.char_start + local_char_start
        global_char_end = chunk.char_start + local_char_end

        local_token_start, local_token_end = _token_range(
            chunk_tokens, local_char_start, local_char_end
        )
        global_token_start = None
        global_token_end = None
        if local_token_start is not None and chunk.token_start is not None:
            global_token_start = chunk.token_start + local_token_start
        if local_token_end is not None and chunk.token_start is not None:
            global_token_end = chunk.token_start + local_token_end

        provenance = provenance_base.model_copy(
            update={
                "chunk_id": chunk.chunk_id,
                "pass_id": chunk.pass_id,
            }
        )

        aligned_extraction = AlignedExtraction(
            entity=candidate.entity,
            text=candidate.text,
            attributes=attributes,
            char_start=global_char_start,
            char_end=global_char_end,
            token_start=global_token_start,
            token_end=global_token_end,
            alignment_status=status,
            confidence=candidate.confidence,
            provenance=provenance,
        )
        aligned.append(aligned_extraction)

    return AlignmentResult(aligned=aligned, unresolved_count=unresolved_count, warnings=warnings)
