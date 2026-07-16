from __future__ import annotations

from typing import Any, Literal

from blackgeorge.core.event import Event
from pydantic import BaseModel, ConfigDict, Field

from sourcery.contracts import EventRecord


def event_to_record(event: Event) -> EventRecord:
    return EventRecord.model_validate(event.model_dump())


class SessionRefinementResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refinement_context: str = ""


class ResolverCanonicalClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity: str
    canonical_text: str
    mention_indices: list[int] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    attributes: dict[str, Any] = Field(default_factory=dict)


class ReconciliationWorkerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["coreference", "resolver"]
    summary: str = ""
    keep_indices: list[int] = Field(default_factory=list)
    canonical_claims: list[ResolverCanonicalClaim] = Field(default_factory=list)
