from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from sourcery.contracts import (
    AlignedExtraction,
    CanonicalClaim,
    DocumentResult,
    EntitySchemaSet,
    EntitySpec,
    ExtractOptions,
    ExtractRequest,
    ExtractionCandidate,
    ExtractionProvenance,
    ExtractionTask,
    ReconciliationConfig,
    RetryPolicy,
    RuntimeConfig,
    SessionRefinementConfig,
    SourceDocument,
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
        model="deepseek/deepseek-v4-pro",
        session_refinement=SessionRefinementConfig(enabled=True, max_turns=2, context_chars=256),
        reconciliation=ReconciliationConfig(enabled=True, use_workforce=True, max_claims=50),
    )

    assert config.session_refinement.enabled is True
    assert config.session_refinement.max_turns == 2
    assert config.reconciliation.enabled is True
    assert config.reconciliation.max_claims == 50


@pytest.mark.parametrize(
    "kwargs",
    [
        {"temperature": -0.1},
        {"max_tokens": 0},
        {"storage_dir": "   "},
    ],
)
def test_runtime_config_rejects_values_blackgeorge_cannot_run(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        RuntimeConfig.model_validate({"model": "deepseek/deepseek-v4-pro", **kwargs})


def test_runtime_config_normalizes_model_route() -> None:
    config = RuntimeConfig(model="  deepseek/deepseek-v4-pro  ")

    assert config.model == "deepseek/deepseek-v4-pro"


def test_extract_request_rejects_duplicate_document_ids(task: ExtractionTask) -> None:
    documents = [
        SourceDocument(document_id="duplicate", text="First"),
        SourceDocument(document_id="duplicate", text="Second"),
    ]

    with pytest.raises(ValidationError):
        ExtractRequest(
            documents=documents,
            task=task,
            runtime=RuntimeConfig(model="deepseek/deepseek-v4-pro"),
        )


def test_extraction_candidate_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        ExtractionCandidate(entity="person", text="Alice", attributes={}, confidence=1.2)


def test_extraction_candidate_serializes_typed_attributes() -> None:
    candidate = ExtractionCandidate(
        entity="person",
        text="Alice",
        attributes=A(value="CEO"),
    )

    assert candidate.model_dump(mode="json")["attributes"] == {"value": "CEO"}


def test_canonical_claim_requires_consistent_mentions() -> None:
    with pytest.raises(ValidationError):
        CanonicalClaim(
            claim_id="claim-1",
            entity="person",
            canonical_text="Alice",
            mention_count=2,
            extraction_indices=[0],
        )


def test_aligned_extraction_rejects_empty_token_range() -> None:
    with pytest.raises(ValidationError):
        AlignedExtraction(
            entity="person",
            text="Alice",
            attributes={},
            char_start=0,
            char_end=5,
            token_start=1,
            token_end=1,
            alignment_status="exact",
            provenance=ExtractionProvenance(
                run_id="run-1",
                pass_id=1,
                chunk_id="chunk-1",
                worker_name="worker",
                model="test/model",
            ),
        )


def test_document_result_rejects_extraction_past_text_end() -> None:
    extraction = AlignedExtraction(
        entity="person",
        text="Alice",
        attributes={},
        char_start=0,
        char_end=6,
        alignment_status="exact",
        provenance=ExtractionProvenance(
            run_id="run-1",
            pass_id=1,
            chunk_id="chunk-1",
            worker_name="worker",
            model="test/model",
        ),
    )

    with pytest.raises(ValidationError, match="exceeds document text"):
        DocumentResult(document_id="doc-1", text="Alice", extractions=[extraction])
