from __future__ import annotations

from collections.abc import Sequence

from sourcery.contracts import ExampleValidationIssue, ExtractionTask
from sourcery.exceptions import ExampleValidationError
from sourcery.pipeline.aligner import _find_exact_span, _fuzzy_span


class ExampleValidator:
    def validate(
        self,
        *,
        task: ExtractionTask,
        fuzzy_threshold: float,
    ) -> list[ExampleValidationIssue]:
        issues: list[ExampleValidationIssue] = []

        for example_index, example in enumerate(task.examples):
            for extraction in example.extractions:
                exact = _find_exact_span(example.text, extraction.text)
                if exact is not None:
                    continue

                fuzzy = _fuzzy_span(example.text, extraction.text, fuzzy_threshold)
                if fuzzy is not None:
                    issues.append(
                        ExampleValidationIssue(
                            example_index=example_index,
                            entity=extraction.entity,
                            text=extraction.text,
                            status="fuzzy",
                            detail="Extraction matches fuzzily but not exactly",
                        )
                    )
                    continue

                issues.append(
                    ExampleValidationIssue(
                        example_index=example_index,
                        entity=extraction.entity,
                        text=extraction.text,
                        status="unresolved",
                        detail="Extraction text not found in example text",
                    )
                )

        return issues

    def enforce_or_warn(
        self,
        *,
        task: ExtractionTask,
        issues: Sequence[ExampleValidationIssue],
    ) -> list[str]:
        warnings: list[str] = []
        unresolved = [issue for issue in issues if issue.status == "unresolved"]
        fuzzy = [issue for issue in issues if issue.status == "fuzzy"]

        if unresolved and task.strict_example_alignment:
            sample = unresolved[0]
            raise ExampleValidationError(
                "Strict example alignment failed: "
                f"example#{sample.example_index} entity='{sample.entity}' text='{sample.text}'"
            )

        for issue in unresolved + fuzzy:
            warnings.append(
                f"Example alignment issue: example#{issue.example_index} "
                f"entity='{issue.entity}' status='{issue.status}' detail='{issue.detail}'"
            )

        return warnings
