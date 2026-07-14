"""Static assertions on the Terraform secret lifecycle (fix-terraform-secret-lifecycle).

The PII keyring and basic-auth secret values must be seeded once and never overwritten by a
routine apply (which would orphan outstanding ENC_ tokens / rotate the live password). Guard the
`ignore_changes` lifecycle and the apply-halting precondition (a `check` block only warns).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_MAIN_TF = Path(__file__).resolve().parents[2] / "deployment" / "terraform" / "main.tf"


@pytest.fixture(scope="module")
def main_tf() -> str:
    return _MAIN_TF.read_text(encoding="utf-8")


def _resource_block(text: str, resource: str) -> str:
    """Return the body of a `resource "<type>" "<name>"` block by brace matching."""
    start = text.index(f'resource "{resource}"')
    depth = 0
    i = text.index("{", start)
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[start : j + 1]
    raise AssertionError(f"unterminated block for {resource}")


@pytest.mark.parametrize(
    "resource",
    [
        'aws_secretsmanager_secret_version" "pii_keyring',
        'aws_secretsmanager_secret_version" "basic_auth',
    ],
)
def test_secret_version_ignores_changes_to_secret_string(main_tf: str, resource: str) -> None:
    block = _resource_block(main_tf, resource)
    assert "ignore_changes" in block, f"{resource} must not be overwritten by a routine apply"
    assert re.search(r"ignore_changes\s*=\s*\[\s*secret_string\s*\]", block), resource


def test_basic_auth_guard_is_a_halting_precondition_not_a_check_block(main_tf: str) -> None:
    # A `check` block only warns; apply must be halted by a precondition/validation.
    assert 'check "basic_auth_credentials_present"' not in main_tf
    task_def = _resource_block(main_tf, 'aws_ecs_task_definition" "this')
    assert "precondition" in task_def
    assert "basic_auth_enabled" in task_def
