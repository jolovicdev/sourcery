from __future__ import annotations

from collections.abc import Sequence
import json
from typing import Any

from sourcery.contracts import (
    EntitySchemaSet,
    ExtractionExample,
    ExtractionTask,
    PromptEnvelope,
    TextChunk,
)


class PromptCompiler:
    def __init__(self, examples: Sequence[ExtractionExample] = ()) -> None:
        self._examples = tuple(examples)

    def with_examples(self, examples: Sequence[ExtractionExample]) -> PromptCompiler:
        return PromptCompiler(examples)

    def compile(
        self,
        task_or_schema: ExtractionTask | EntitySchemaSet,
        chunk: TextChunk,
        pass_id: int,
        *,
        instructions: str | None = None,
        examples: Sequence[ExtractionExample] | None = None,
        refinement_context: str | None = None,
    ) -> PromptEnvelope:
        task_examples: Sequence[ExtractionExample]
        if isinstance(task_or_schema, ExtractionTask):
            task_instructions = task_or_schema.instructions
            schema_set = task_or_schema.entity_schema
            task_examples = task_or_schema.examples
        else:
            task_instructions = instructions or ""
            schema_set = task_or_schema
            task_examples = self._examples if examples is None else examples

        schema_rows = [
            {
                "entity": entity.name,
                "attributes": list(entity.attributes_model.model_fields),
            }
            for entity in schema_set.entities
        ]
        schema_summary = "Allowed entities:\n" + json.dumps(
            schema_rows, ensure_ascii=False, indent=2
        )
        examples_block = ""
        if task_examples:
            rendered_examples = [
                {
                    "text": example.text,
                    "extractions": [
                        {
                            "entity": extraction.entity,
                            "text": extraction.text,
                            "attributes": extraction.attributes,
                        }
                        for extraction in example.extractions
                    ],
                }
                for example in task_examples
            ]
            examples_block = "Few-shot examples:\n" + json.dumps(
                rendered_examples, ensure_ascii=False, indent=2
            )
        system = "\n\n".join(
            part
            for part in [
                task_instructions.strip(),
                "Return JSON that matches the response schema exactly.",
                "Use verbatim text spans from the chunk.",
                schema_summary,
                examples_block,
            ]
            if part
        )

        user_payload: dict[str, Any] = {
            "pass_id": pass_id,
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "chunk_text": chunk.text,
        }
        if chunk.previous_context:
            user_payload["previous_context"] = chunk.previous_context
        if refinement_context:
            user_payload["refinement_context"] = refinement_context

        user = json.dumps(user_payload, ensure_ascii=False, indent=2)
        schema_data = {
            "entities": [
                {
                    "name": entity.name,
                    "attributes_model": entity.attributes_model.__name__,
                }
                for entity in schema_set.entities
            ]
        }
        return PromptEnvelope.from_components(system=system, user=user, schema_data=schema_data)
