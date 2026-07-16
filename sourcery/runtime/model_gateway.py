from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

from sourcery.contracts import EntitySchemaSet, ExtractionCandidate
from sourcery.exceptions import RuntimeIntegrationError


def _normalize_entity_name(name: str) -> str:
    normalized = "".join(char for char in name.title() if char.isalnum())
    return normalized or "Entity"


def _schema_digest(entities: tuple[tuple[str, type[BaseModel]], ...]) -> str:
    payload = [
        {
            "entity": name,
            "attributes_model": f"{model.__module__}.{model.__qualname__}",
            "schema": model.model_json_schema(),
        }
        for name, model in entities
    ]
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()[:12]


@lru_cache(maxsize=None)
def _build_chunk_candidate_schema(
    entities: tuple[tuple[str, type[BaseModel]], ...],
) -> type[BaseModel]:
    digest = _schema_digest(entities)
    variants: list[type[BaseModel]] = []

    for entity_name, attributes_model in entities:
        model_name = f"{_normalize_entity_name(entity_name)}Candidate_{digest}"
        variant = create_model(
            model_name,
            __config__=ConfigDict(extra="forbid"),
            __module__=__name__,
            entity=(Literal[entity_name], ...),
            text=(str, ...),
            attributes=(attributes_model, ...),
            confidence=(float | None, Field(default=None, ge=0.0, le=1.0)),
        )
        variants.append(variant)

    candidate_type: Any = variants[0]
    for variant in variants[1:]:
        candidate_type = candidate_type | variant

    model_name = f"ChunkCandidateSchema_{digest}"
    model = create_model(
        model_name,
        __config__=ConfigDict(extra="forbid"),
        __module__=__name__,
        extractions=(list[candidate_type], Field(default_factory=list)),
    )
    globals()[model_name] = model
    return model


def build_chunk_candidate_schema(schema_set: EntitySchemaSet) -> type[BaseModel]:
    entities = tuple((entity.name, entity.attributes_model) for entity in schema_set.entities)
    return _build_chunk_candidate_schema(entities)


def parse_candidates_from_structured_data(data_obj: Any) -> list[ExtractionCandidate]:
    if data_obj is None:
        return []

    if isinstance(data_obj, dict):
        raw_items = data_obj.get("extractions", [])
    elif isinstance(data_obj, BaseModel):
        model_data = data_obj.model_dump()
        raw_items = model_data.get("extractions", [])
    else:
        raise RuntimeIntegrationError(
            f"Unsupported structured extraction payload: {type(data_obj).__name__}"
        )
    if not isinstance(raw_items, list):
        raise RuntimeIntegrationError("Structured extraction payload must contain a list")

    candidates: list[ExtractionCandidate] = []
    for item in raw_items:
        if isinstance(item, BaseModel):
            payload = item.model_dump()
        else:
            payload = dict(item)
        candidates.append(ExtractionCandidate.model_validate(payload))

    return candidates
