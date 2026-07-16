from __future__ import annotations

from collections.abc import Iterable
from difflib import SequenceMatcher
import re

from pydantic import BaseModel, Field, ValidationError

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
    warnings: list[str] = Field(default_factory=list)


def find_exact_span(text: str, query: str, start: int = 0) -> tuple[int, int] | None:
    pattern = re.escape(query)
    match = re.search(pattern, text[start:], flags=re.IGNORECASE)
    if match is None:
        return None
    return start + match.start(), start + match.end()


def _normalize_token(token: str) -> str:
    normalized = token.lower()
    if len(normalized) > 3 and normalized.endswith("s") and not normalized.endswith("ss"):
        normalized = normalized[:-1]
    return normalized


def find_fuzzy_span(text: str, query: str, threshold: float) -> tuple[int, int] | None:
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
    text_tokens = [
        token
        for token in tokenize_with_spans(text)
        if any(character.isalnum() for character in token.token)
    ]
    query_tokens = [
        token
        for token in tokenize_with_spans(query)
        if any(character.isalnum() for character in token.token)
    ]
    if not text_tokens or len(query_tokens) < 2:
        return None

    previous_lengths = [0] * (len(query_tokens) + 1)
    best_length = 0
    best_text_end = 0
    for text_index, text_token in enumerate(text_tokens, start=1):
        current_lengths = [0] * (len(query_tokens) + 1)
        normalized_text = text_token.token.casefold()
        for query_index, query_token in enumerate(query_tokens, start=1):
            if normalized_text != query_token.token.casefold():
                continue
            current_lengths[query_index] = previous_lengths[query_index - 1] + 1
            if current_lengths[query_index] > best_length:
                best_length = current_lengths[query_index]
                best_text_end = text_index
        previous_lengths = current_lengths

    if best_length < 2 or best_length * 2 <= len(query_tokens):
        return None

    start_token = text_tokens[best_text_end - best_length]
    end_token = text_tokens[best_text_end - 1]
    return start_token.char_start, end_token.char_end


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
) -> tuple[BaseModel | None, str | None]:
    by_name = schema.by_name()
    entity_spec = by_name.get(candidate.entity)
    if entity_spec is None:
        return None, f"Unknown entity '{candidate.entity}' from model output"

    try:
        attributes = (
            candidate.attributes.model_dump()
            if isinstance(candidate.attributes, BaseModel)
            else candidate.attributes
        )
        validated = entity_spec.attributes_model.model_validate(attributes)
        return validated, None
    except ValidationError as exc:
        return None, f"Invalid attributes for entity '{candidate.entity}': {exc}"


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
    exact_search_starts: dict[tuple[str, str], int] = {}

    chunk_tokens = tokenize_with_spans(chunk.text)

    for candidate in candidates:
        attributes, attributes_warning = _coerce_attributes(candidate, schema)
        if attributes_warning is not None:
            warnings.append(attributes_warning)
        if attributes is None:
            continue

        status: AlignmentStatus = "unresolved"
        candidate_key = (candidate.entity, candidate.text.casefold())
        search_start = exact_search_starts.get(candidate_key, 0)
        span = find_exact_span(chunk.text, candidate.text, search_start)
        if span is not None:
            status = "exact"
            exact_search_starts[candidate_key] = span[1]
        elif search_start:
            warnings.append(
                f"Duplicate candidate '{candidate.entity}:{candidate.text}' exceeds source occurrences"
            )
            continue
        elif options.enable_fuzzy_alignment:
            span = find_fuzzy_span(chunk.text, candidate.text, options.fuzzy_alignment_threshold)
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
