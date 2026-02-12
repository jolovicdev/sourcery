from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
import uuid

from pydantic import BaseModel, Field

from sourcery.contracts import EventRecord


def event_to_record(event: Any) -> EventRecord:
    timestamp = getattr(event, "timestamp", None)
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    return EventRecord(
        event_id=str(getattr(event, "event_id", uuid.uuid4().hex)),
        type=str(getattr(event, "type", "unknown")),
        timestamp=timestamp,
        run_id=str(getattr(event, "run_id", "unknown")),
        source=str(getattr(event, "source", "unknown")),
        payload=dict(getattr(event, "payload", {}) or {}),
    )


class SessionRefinementPayload(BaseModel):
    chunk_id: str
    document_id: str
    pass_id: int
    chunk_text: str
    previous_context: str | None = None


class SessionRefinementResult(BaseModel):
    refinement_context: str = ""


class ResolverCanonicalClaim(BaseModel):
    entity: str
    canonical_text: str
    mention_indices: list[int] = Field(default_factory=list)
    confidence: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ReconciliationWorkerOutput(BaseModel):
    mode: Literal["coreference", "resolver"]
    summary: str = ""
    keep_indices: list[int] = Field(default_factory=list)
    canonical_claims: list[ResolverCanonicalClaim] = Field(default_factory=list)
