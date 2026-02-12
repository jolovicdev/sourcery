from __future__ import annotations

from pydantic import BaseModel

from sourcery.contracts import EntitySchemaSet, EntitySpec
from sourcery.runtime.model_gateway import (
    build_chunk_candidate_schema,
    parse_candidates_from_structured_data,
)


class Person(BaseModel):
    role: str


class Organization(BaseModel):
    industry: str


def test_build_chunk_candidate_schema_and_parse() -> None:
    schema = EntitySchemaSet(
        entities=[
            EntitySpec(name="person", attributes_model=Person),
            EntitySpec(name="organization", attributes_model=Organization),
        ]
    )
    chunk_schema = build_chunk_candidate_schema(schema)

    instance = chunk_schema.model_validate(
        {
            "extractions": [
                {
                    "entity": "person",
                    "text": "Alice",
                    "attributes": {"role": "CEO"},
                    "confidence": 0.98,
                }
            ]
        }
    )

    candidates = parse_candidates_from_structured_data(instance)
    assert len(candidates) == 1
    assert candidates[0].entity == "person"
    assert candidates[0].confidence == 0.98
