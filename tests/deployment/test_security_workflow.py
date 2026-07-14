"""Static contracts for the pull-request security workflow."""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SECURITY_WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "security.yml"


def _workflow() -> dict:
    loaded = yaml.safe_load(SECURITY_WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _step(job: dict, name: str) -> dict:
    return next(step for step in job["steps"] if step.get("name") == name)


def test_codeql_job_can_checkout_and_upload_results() -> None:
    permissions = _workflow()["jobs"]["codeql"]["permissions"]
    assert permissions == {"contents": "read", "security-events": "write"}


def test_gitleaks_uses_pinned_oss_scanner_on_full_history() -> None:
    workflow = _workflow()
    job = workflow["jobs"]["gitleaks"]
    checkout = _step(job, "Checkout")
    scan = _step(job, "Run gitleaks")

    assert checkout["with"]["fetch-depth"] == 0
    assert scan["uses"] == "docker://ghcr.io/gitleaks/gitleaks:v8.21.2"
    args = scan["with"]["args"]
    assert "detect" in args
    assert "--source=/github/workspace" in args
    assert "--redact" in args

    workflow_text = SECURITY_WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "GITLEAKS_LICENSE" not in workflow_text
    assert "gitleaks/gitleaks-action" not in workflow_text


def test_dependency_audit_scans_locked_third_party_packages() -> None:
    job = _workflow()["jobs"]["dependency-audit"]
    export = _step(job, "Export locked requirements")["run"]
    audit = _step(job, "Audit dependencies")["run"]

    assert "--no-emit-project" in export
    assert "--no-dev" in export
    assert "--disable-pip" in audit
    assert "-r requirements.txt" in audit
