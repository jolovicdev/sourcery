from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AlignmentStatus = Literal["exact", "fuzzy", "partial", "unresolved"]


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex}"


def new_document_id() -> str:
    return f"doc_{uuid.uuid4().hex[:10]}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_sequence(value: Any) -> Any:
    return value


class SourceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    document_id: str = Field(default_factory=new_document_id)
    additional_context: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def validate_text_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Document text must not be empty")
        return value


class TextChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    pass_id: int
    order_index: int
    text: str
    char_start: int
    char_end: int
    token_start: int | None = None
    token_end: int | None = None
    previous_context: str | None = None

    @model_validator(mode="after")
    def validate_ranges(self) -> TextChunk:
        if self.char_start < 0 or self.char_end < 0:
            raise ValueError("Chunk char offsets must be non-negative")
        if self.char_start >= self.char_end:
            raise ValueError("Chunk char range must be non-empty")
        if self.pass_id < 1:
            raise ValueError("Chunk pass_id must be >= 1")
        if self.order_index < 0:
            raise ValueError("Chunk order_index must be >= 0")
        if not self.text:
            raise ValueError("Chunk text must not be empty")
        return self


class ExampleExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity: str
    text: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class ExtractionExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    extractions: list[ExampleExtraction] = Field(default_factory=list)


class EntitySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    attributes_model: type[BaseModel]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Entity name must not be empty")
        return stripped

    @field_validator("attributes_model")
    @classmethod
    def validate_attributes_model(cls, value: type[BaseModel]) -> type[BaseModel]:
        if not isinstance(value, type) or not issubclass(value, BaseModel):
            raise TypeError("attributes_model must be a Pydantic BaseModel subclass")
        return value


class EntitySchemaSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[EntitySpec]

    @model_validator(mode="after")
    def validate_unique_entities(self) -> EntitySchemaSet:
        if not self.entities:
            raise ValueError("At least one entity spec is required")
        names = [entity.name for entity in self.entities]
        if len(set(names)) != len(names):
            raise ValueError("Entity names must be unique")
        return self

    def by_name(self) -> dict[str, EntitySpec]:
        return {entity.name: entity for entity in self.entities}


class ExtractionTask(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    instructions: str
    entity_schema: EntitySchemaSet = Field(alias="schema")
    examples: list[ExtractionExample]
    strict_example_alignment: bool = True

    @field_validator("instructions")
    @classmethod
    def validate_instructions_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Task instructions must not be empty")
        return value

    @model_validator(mode="after")
    def validate_examples_present(self) -> ExtractionTask:
        if not self.examples:
            raise ValueError("At least one extraction example is required")
        return self


class ExtractOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_chunk_chars: int = 1200
    context_window_chars: int = 200
    max_passes: int = 2
    batch_concurrency: int = 16
    enable_fuzzy_alignment: bool = True
    fuzzy_alignment_threshold: float = 0.82
    accept_partial_exact: bool = False
    stop_when_no_new_extractions: bool = True
    allow_unresolved: bool = False

    @model_validator(mode="after")
    def validate_options(self) -> ExtractOptions:
        if self.max_chunk_chars < 100:
            raise ValueError("max_chunk_chars must be >= 100")
        if self.context_window_chars < 0:
            raise ValueError("context_window_chars must be >= 0")
        if self.max_passes < 1:
            raise ValueError("max_passes must be >= 1")
        if self.batch_concurrency < 1:
            raise ValueError("batch_concurrency must be >= 1")
        if not (0.0 <= self.fuzzy_alignment_threshold <= 1.0):
            raise ValueError("fuzzy_alignment_threshold must be in [0.0, 1.0]")
        return self


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_attempts: int = 3
    initial_backoff_seconds: float = 0.75
    max_backoff_seconds: float = 8.0
    backoff_multiplier: float = 2.0
    retry_on_rate_limit: bool = True
    retry_on_transient_errors: bool = True
    auto_resume_paused_runs: bool = True
    max_pause_resumes: int = 5

    @model_validator(mode="after")
    def validate_retry_policy(self) -> RetryPolicy:
        if self.max_attempts < 1:
            raise ValueError("retry.max_attempts must be >= 1")
        if self.initial_backoff_seconds < 0:
            raise ValueError("retry.initial_backoff_seconds must be >= 0")
        if self.max_backoff_seconds < self.initial_backoff_seconds:
            raise ValueError("retry.max_backoff_seconds must be >= retry.initial_backoff_seconds")
        if self.backoff_multiplier < 1.0:
            raise ValueError("retry.backoff_multiplier must be >= 1.0")
        if self.max_pause_resumes < 0:
            raise ValueError("retry.max_pause_resumes must be >= 0")
        return self


class SessionRefinementConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    max_turns: int = 1
    context_chars: int = 320

    @model_validator(mode="after")
    def validate_session_refinement(self) -> SessionRefinementConfig:
        if self.max_turns < 1:
            raise ValueError("session_refinement.max_turns must be >= 1")
        if self.context_chars < 32:
            raise ValueError("session_refinement.context_chars must be >= 32")
        return self


class ReconciliationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    use_workforce: bool = True
    min_mentions_for_claim: int = 1
    max_claims: int = 200

    @model_validator(mode="after")
    def validate_reconciliation(self) -> ReconciliationConfig:
        if self.min_mentions_for_claim < 1:
            raise ValueError("reconciliation.min_mentions_for_claim must be >= 1")
        if self.max_claims < 1:
            raise ValueError("reconciliation.max_claims must be >= 1")
        return self


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    temperature: float = 0.0
    max_tokens: int | None = None
    stream: bool = False
    storage_dir: str = ".sourcery"
    respect_context_window: bool = True
    retry: RetryPolicy = Field(default_factory=RetryPolicy)
    session_refinement: SessionRefinementConfig = Field(default_factory=SessionRefinementConfig)
    reconciliation: ReconciliationConfig = Field(default_factory=ReconciliationConfig)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("runtime.model must not be empty")
        return value


class ExtractionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity: str
    text: str
    attributes: dict[str, Any] | BaseModel
    confidence: float | None = None


class ExtractionProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    pass_id: int
    chunk_id: str
    worker_name: str
    model: str
    step_name: str | None = None
    raw_run_id: str | None = None


class AlignedExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity: str
    text: str
    attributes: dict[str, Any] | BaseModel
    char_start: int
    char_end: int
    token_start: int | None = None
    token_end: int | None = None
    alignment_status: AlignmentStatus
    confidence: float | None = None
    provenance: ExtractionProvenance

    @model_validator(mode="after")
    def validate_alignment(self) -> AlignedExtraction:
        if self.char_start < 0 or self.char_end < 0:
            raise ValueError("Extraction char offsets must be non-negative")
        if self.char_start > self.char_end:
            raise ValueError("Extraction char_start must be <= char_end")
        if self.alignment_status != "unresolved" and self.char_start == self.char_end:
            raise ValueError("Resolved extraction must have a non-empty char span")
        if (
            self.token_start is not None
            and self.token_end is not None
            and self.token_start > self.token_end
        ):
            raise ValueError("token_start must be <= token_end")
        return self


class CanonicalClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    entity: str
    canonical_text: str
    mention_count: int
    extraction_indices: list[int] = Field(default_factory=list)
    confidence: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_canonical_claim(self) -> CanonicalClaim:
        if not self.claim_id.strip():
            raise ValueError("Canonical claim id must not be empty")
        if not self.entity.strip():
            raise ValueError("Canonical claim entity must not be empty")
        if not self.canonical_text.strip():
            raise ValueError("Canonical claim text must not be empty")
        if self.mention_count < 1:
            raise ValueError("Canonical claim mention_count must be >= 1")
        return self


class DocumentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    text: str
    extractions: list[AlignedExtraction] = Field(default_factory=list)
    canonical_claims: list[CanonicalClaim] = Field(default_factory=list)


class RunMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents_total: int = 0
    chunks_total: int = 0
    passes_executed: int = 0
    candidates_total: int = 0
    extracted_total: int = 0
    unresolved_total: int = 0
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    type: str
    timestamp: datetime
    run_id: str
    source: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ChunkExtractionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    pass_id: int
    chunk: TextChunk
    candidates: list[ExtractionCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    events: list[EventRecord] = Field(default_factory=list)
    worker_name: str = "ExtractorWorker"
    model: str
    raw_run_id: str | None = None


class DocumentReconciliationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    reconciled_extractions: list[AlignedExtraction] = Field(default_factory=list)
    canonical_claims: list[CanonicalClaim] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    events: list[EventRecord] = Field(default_factory=list)
    raw_run_id: str | None = None


class ExtractionRunTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=new_run_id)
    model: str
    chunk_ids: list[str] = Field(default_factory=list)
    pass_ids: list[int] = Field(default_factory=list)
    events: list[EventRecord] = Field(default_factory=list)


class ExtractResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[DocumentResult]
    run_trace: ExtractionRunTrace
    metrics: RunMetrics
    warnings: list[str] = Field(default_factory=list)


class ExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[SourceDocument] | str
    task: ExtractionTask
    options: ExtractOptions = Field(default_factory=ExtractOptions)
    runtime: RuntimeConfig

    def normalize_documents(self) -> list[SourceDocument]:
        if isinstance(self.documents, str):
            return [SourceDocument(text=self.documents)]
        return list(self.documents)


class PromptEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system: str
    user: str
    schema_payload: str

    @classmethod
    def from_components(cls, system: str, user: str, schema_data: dict[str, Any]) -> PromptEnvelope:
        return cls(
            system=system,
            user=user,
            schema_payload=json.dumps(schema_data, indent=2, sort_keys=True),
        )


class ChunkRuntimeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    pass_id: int
    chunk: TextChunk
    task: ExtractionTask
    runtime: RuntimeConfig
    options: ExtractOptions


class EngineDependencies(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    runtime_factory: Any
    prompt_compiler: Any
    example_validator: Any
    chunk_planner: Any
    aligner: Any
    merger: Any
    trace_collector_factory: Any


class ExampleValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    example_index: int
    entity: str
    text: str
    status: AlignmentStatus
    detail: str
