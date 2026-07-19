from __future__ import annotations

import re
from pathlib import Path

import yaml


WORKFLOW = Path(".github/workflows/ci.yml")
CHECKOUT_SHA = "9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0"
SETUP_PYTHON_SHA = "ece7cb06caefa5fff74198d8649806c4678c61a1"


def _workflow_text() -> str:
    assert WORKFLOW.is_file(), "general push/PR CI workflow is missing"
    return WORKFLOW.read_text(encoding="utf-8")


def _workflow_config() -> dict[str, object]:
    parsed = yaml.load(_workflow_text(), Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    return parsed


def test_general_ci_runs_on_every_push_and_pull_request() -> None:
    config = _workflow_config()

    triggers = config["on"]
    assert isinstance(triggers, dict)
    assert set(triggers) == {"push", "pull_request"}
    # BaseLoader preserves empty YAML scalars as "" (safe_load uses None).
    assert triggers["push"] in (None, "")
    assert triggers["pull_request"] in (None, "")


def test_general_ci_is_read_only_and_uses_pinned_actions() -> None:
    config = _workflow_config()
    text = _workflow_text()

    assert config["permissions"] == {"contents": "read"}
    jobs = config["jobs"]
    assert isinstance(jobs, dict)
    test_job = jobs["test"]
    assert isinstance(test_job, dict)
    steps = test_job["steps"]
    assert isinstance(steps, list)
    assert [step["name"] for step in steps] == [
        "Checkout",
        "Set up Python 3.12",
        "Install and test",
    ]
    checkout_steps = [
        step
        for step in steps
        if isinstance(step, dict)
        and str(step.get("uses", "")).startswith("actions/checkout@")
    ]
    assert checkout_steps == [
        {
            "name": "Checkout",
            "uses": f"actions/checkout@{CHECKOUT_SHA}",
            "with": {"persist-credentials": "false"},
        }
    ]
    action_refs = re.findall(r"^\s*uses:\s*([^\s]+)\s*$", text, re.MULTILINE)
    assert action_refs == [
        f"actions/checkout@{CHECKOUT_SHA}",
        f"actions/setup-python@{SETUP_PYTHON_SHA}",
    ]
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", ref) for ref in action_refs)


def test_general_ci_installs_both_requirements_and_runs_canonical_suite() -> None:
    config = _workflow_config()
    text = _workflow_text()

    assert 'python-version: "3.12"' in text
    assert "requirements-nwp.txt" in text
    assert "requirements-cov.txt" in text
    assert (
        "python -m pytest tests/unit tests/leakage tests/integration -q"
        in text
    )
    test_job = config["jobs"]["test"]
    run_script = test_job["steps"][2]["run"]
    assert [line.strip() for line in run_script.splitlines() if line.strip()] == [
        "set -Eeuo pipefail",
        "python -m pip install --disable-pip-version-check \\",
        "-r requirements-nwp.txt \\",
        "-r requirements-cov.txt",
        "git diff --check",
        "python -m pytest tests/unit tests/leakage tests/integration -q",
    ]


def test_general_ci_has_no_credentials_or_external_evidence_paths() -> None:
    text = _workflow_text()

    for forbidden in (
        "secrets",
        "vars",
        "RCLONE_CONFIG",
        "rclone",
        "raw_data",
        "Data Weather Station",
        "NWP_DESTINATION",
        "upload-artifact",
        "src/models",
        "src/features",
    ):
        assert forbidden not in text
