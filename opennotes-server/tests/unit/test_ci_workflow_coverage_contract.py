from pathlib import Path

import yaml


def _load_ci_workflow() -> dict:
    workflow_path = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "ci.yml"
    with workflow_path.open(encoding="utf-8") as workflow_file:
        return yaml.safe_load(workflow_file)


def _step_by_name(steps: list[dict], name: str) -> dict:
    return next(step for step in steps if step.get("name") == name)


def test_unit_test_job_generates_the_report_uploaded_to_codecov() -> None:
    workflow = _load_ci_workflow()
    unit_job = workflow["jobs"]["unit-tests-python"]
    steps = unit_job["steps"]

    test_step = _step_by_name(steps, "Run unit tests with coverage")
    upload_step = _step_by_name(steps, "Upload coverage to Codecov")

    assert upload_step["with"]["files"] == "opennotes-server/coverage.xml"
    assert "--cov=src" in test_step["run"]
    assert "--cov-report=xml" in test_step["run"]
