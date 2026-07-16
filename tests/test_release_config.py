from __future__ import annotations

from pathlib import Path
import re
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_is_ready_for_0_3_0() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    locked_project = next(
        package for package in lock["package"] if package["name"] == project["name"]
    )

    assert project["version"] == "0.3.0"
    assert locked_project["version"] == project["version"]
    assert project["urls"]["Repository"] == "https://github.com/jolovicdev/sourcery"
    assert "repository" not in project


def test_manual_publish_is_safe_by_default() -> None:
    workflow = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")

    assert re.search(r"workflow_dispatch:.*?dry_run:.*?default: \"true\"", workflow, re.DOTALL)
    assert (
        "if: github.event_name == 'workflow_dispatch' && github.event.inputs.dry_run != 'true'"
    ) in workflow
    assert 'if [ "${GITHUB_REF}" != "refs/heads/master" ]; then' in workflow
    assert (
        "if: github.event_name != 'workflow_dispatch' || github.event.inputs.dry_run != 'true'"
    ) in workflow
