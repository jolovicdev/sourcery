from __future__ import annotations

import pytest

from sourcery.contracts import ExtractionTask
from sourcery.exceptions import ExampleValidationError
from sourcery.pipeline.example_validator import ExampleValidator


def test_example_validator_finds_unresolved(task: ExtractionTask) -> None:
    validator = ExampleValidator()
    task.examples[0].extractions[0].text = "NotInText"

    issues = validator.validate(task=task, fuzzy_threshold=0.82)
    assert issues
    assert any(issue.status == "unresolved" for issue in issues)


def test_example_validator_strict_raises(task: ExtractionTask) -> None:
    validator = ExampleValidator()
    task.examples[0].extractions[0].text = "NotInText"

    issues = validator.validate(task=task, fuzzy_threshold=0.82)

    with pytest.raises(ExampleValidationError):
        validator.enforce_or_warn(task=task, issues=issues)


def test_example_validator_warn_mode(task: ExtractionTask) -> None:
    validator = ExampleValidator()
    task.strict_example_alignment = False
    task.examples[0].extractions[0].text = "NotInText"

    issues = validator.validate(task=task, fuzzy_threshold=0.82)
    warnings = validator.enforce_or_warn(task=task, issues=issues)

    assert warnings


def test_example_validator_flags_unknown_entity(task: ExtractionTask) -> None:
    validator = ExampleValidator()
    task.examples[0].extractions[0].entity = "company"

    issues = validator.validate(task=task, fuzzy_threshold=0.82)
    assert any("company" in issue.entity for issue in issues)
    assert any("not in schema" in issue.detail.lower() for issue in issues)


def test_example_validator_allows_known_entities(task: ExtractionTask) -> None:
    validator = ExampleValidator()
    issues = validator.validate(task=task, fuzzy_threshold=0.82)
    assert not issues
