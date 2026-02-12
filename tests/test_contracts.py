from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from sourcery.contracts import (
    EntitySchemaSet,
    EntitySpec,
    ExtractOptions,
    ExtractionTask,
    ReconciliationConfig,
    RetryPolicy,
    RuntimeConfig,
    SessionRefinementConfig,
)


class A(BaseModel):
    value: str


class B(BaseModel):
    value: str


class NotPydantic:
    value: str


def test_entity_spec_requires_pydantic_model() -> None:
    with pytest.raises(ValidationError):
        EntitySpec(name="bad", attributes_model=NotPydantic)  # type: ignore[arg-type]


def test_entity_schema_requires_unique_names() -> None:
    with pytest.raises(ValueError):
        EntitySchemaSet(
            entities=[
                EntitySpec(name="a", attributes_model=A),
                EntitySpec(name="a", attributes_model=B),
            ]
        )


def test_extract_options_validates_threshold() -> None:
    with pytest.raises(ValueError):
        ExtractOptions(fuzzy_alignment_threshold=1.5)


def test_extraction_task_requires_examples() -> None:
    schema = EntitySchemaSet(entities=[EntitySpec(name="person", attributes_model=A)])
    with pytest.raises(ValueError):
        ExtractionTask(instructions="x", schema=schema, examples=[])


def test_runtime_config_requires_model() -> None:
    with pytest.raises(ValueError):
        RuntimeConfig(model="")


def test_retry_policy_validates_attempts() -> None:
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)


def test_session_refinement_config_validates_turns() -> None:
    with pytest.raises(ValueError):
        SessionRefinementConfig(max_turns=0)


def test_reconciliation_config_validates_limits() -> None:
    with pytest.raises(ValueError):
        ReconciliationConfig(max_claims=0)


def test_runtime_config_accepts_refinement_and_reconciliation() -> None:
    config = RuntimeConfig(
        model="deepseek/deepseek-chat",
        session_refinement=SessionRefinementConfig(enabled=True, max_turns=2, context_chars=256),
        reconciliation=ReconciliationConfig(enabled=True, use_workforce=True, max_claims=50),
    )

    assert config.session_refinement.enabled is True
    assert config.session_refinement.max_turns == 2
    assert config.reconciliation.enabled is True
    assert config.reconciliation.max_claims == 50
