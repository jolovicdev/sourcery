from __future__ import annotations

import pytest
from blackgeorge import Job
from pydantic import BaseModel, ValidationError

from sourcery.contracts import EntitySchemaSet, EntitySpec
from sourcery.exceptions import RuntimeIntegrationError
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


def test_chunk_candidate_schema_survives_blackgeorge_job_persistence() -> None:
    schema = EntitySchemaSet(entities=[EntitySpec(name="person", attributes_model=Person)])
    chunk_schema = build_chunk_candidate_schema(schema)
    job = Job(input="extract", response_schema=chunk_schema)

    restored = Job.model_validate_json(job.model_dump_json())

    assert restored.response_schema is chunk_schema


def test_chunk_candidate_schema_rejects_extra_fields_and_invalid_confidence() -> None:
    schema = EntitySchemaSet(entities=[EntitySpec(name="person", attributes_model=Person)])
    chunk_schema = build_chunk_candidate_schema(schema)

    with pytest.raises(ValidationError):
        chunk_schema.model_validate(
            {
                "extractions": [
                    {
                        "entity": "person",
                        "text": "Alice",
                        "attributes": {"role": "CEO"},
                        "confidence": 1.1,
                        "unexpected": True,
                    }
                ]
            }
        )


def test_parse_candidates_rejects_unknown_payload_objects() -> None:
    with pytest.raises(RuntimeIntegrationError, match="Unsupported structured"):
        parse_candidates_from_structured_data(object())
