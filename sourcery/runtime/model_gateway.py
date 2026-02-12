from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, create_model

from sourcery.contracts import EntitySchemaSet, ExtractionCandidate


def _normalize_entity_name(name: str) -> str:
    normalized = "".join(char for char in name.title() if char.isalnum())
    return normalized or "Entity"


def build_chunk_candidate_schema(schema_set: EntitySchemaSet) -> type[BaseModel]:
    variants: list[type[BaseModel]] = []

    for entity in schema_set.entities:
        model_name = f"{_normalize_entity_name(entity.name)}Candidate"
        variant = create_model(
            model_name,
            entity=(Literal[entity.name], ...),
            text=(str, ...),
            attributes=(entity.attributes_model, ...),
            confidence=(float | None, None),
        )
        variants.append(variant)

    if not variants:
        raise ValueError("At least one entity spec is required to build candidate schema")

    candidate_type: Any = variants[0]
    for variant in variants[1:]:
        candidate_type = candidate_type | variant

    return create_model(
        "ChunkCandidateSchema",
        extractions=(list[candidate_type], Field(default_factory=list)),
    )


def parse_candidates_from_structured_data(data_obj: Any) -> list[ExtractionCandidate]:
    if data_obj is None:
        return []

    if isinstance(data_obj, dict):
        raw_items = data_obj.get("extractions", [])
    elif isinstance(data_obj, BaseModel):
        model_data = data_obj.model_dump()
        raw_items = model_data.get("extractions", [])
    else:
        raw_items = getattr(data_obj, "extractions", [])

    candidates: list[ExtractionCandidate] = []
    for item in raw_items:
        if isinstance(item, BaseModel):
            payload = item.model_dump()
        else:
            payload = dict(item)
        candidate = ExtractionCandidate(
            entity=payload["entity"],
            text=payload["text"],
            attributes=payload.get("attributes", {}),
            confidence=payload.get("confidence"),
        )
        candidates.append(candidate)

    return candidates
