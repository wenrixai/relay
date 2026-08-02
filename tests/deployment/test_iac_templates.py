"""Assert the self-hosting IaC templates keep their hardened defaults.

These guard the properties Snyk IaC flagged (see `/.snyk`): customer-managed encryption on the
secrets and log group, no auto-assigned public IPs, and an ALB egress rule scoped to the task
security group. They parse the templates as text/YAML — nothing is deployed and no AWS
credentials are needed.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

DEPLOYMENT_DIR = Path(__file__).resolve().parents[2] / "deployment"
CFN_TEMPLATE = DEPLOYMENT_DIR / "cloudformation" / "wenrix-relay.yaml"
TF_MAIN = DEPLOYMENT_DIR / "terraform" / "main.tf"
TF_VARIABLES = DEPLOYMENT_DIR / "terraform" / "variables.tf"

# Resources that must be encrypted with the stack's KMS key when one is in play.
_CFN_ENCRYPTED_RESOURCES = ("PiiKeyringSecret", "BasicAuthSecret", "LogGroup")


class _CfnLoader(yaml.SafeLoader):
    """Loads CloudFormation YAML, keeping `!Ref`/`!Sub`/`!If`/... as plain data.

    SafeLoader rejects the short-form intrinsic tags outright. Representing each as
    ``{"Fn::If": [...]}`` (or ``{"Ref": ...}``) matches CloudFormation's own long form, so
    assertions can look inside them.
    """


def _intrinsic(loader: yaml.Loader, suffix: str, node: yaml.Node) -> dict[str, Any]:
    key = suffix if suffix == "Ref" else f"Fn::{suffix}"
    if isinstance(node, yaml.ScalarNode):
        value: Any = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    elif isinstance(node, yaml.MappingNode):
        value = loader.construct_mapping(node, deep=True)
    else:  # pragma: no cover - YAML has no fourth node kind
        raise TypeError(f"unexpected node for !{suffix}: {type(node).__name__}")
    return {key: value}


_CfnLoader.add_multi_constructor("!", _intrinsic)


@pytest.fixture(scope="module")
def cfn() -> dict[str, Any]:
    return yaml.load(CFN_TEMPLATE.read_text(encoding="utf-8"), Loader=_CfnLoader)  # noqa: S506


@pytest.fixture(scope="module")
def tf_main() -> str:
    return TF_MAIN.read_text(encoding="utf-8")


def _resource(cfn: dict[str, Any], name: str) -> dict[str, Any]:
    return cfn["Resources"][name]


# --- CloudFormation ---------------------------------------------------------


@pytest.mark.parametrize("name", _CFN_ENCRYPTED_RESOURCES)
def test_cfn_secrets_and_logs_take_the_kms_key(cfn: dict[str, Any], name: str) -> None:
    """Each secret and the log group is encrypted with the CMK, or omits the key entirely."""
    key_id = _resource(cfn, name)["Properties"]["KmsKeyId"]
    # !If [HasKmsKey, <arn>, !Ref AWS::NoValue] — no unconditional fallback to the AWS-managed key.
    branches = key_id["Fn::If"]
    assert branches[0] == "HasKmsKey"
    assert branches[2] == {"Ref": "AWS::NoValue"}


def test_cfn_creates_a_rotating_kms_key_by_default(cfn: dict[str, Any]) -> None:
    assert cfn["Parameters"]["CreateKmsKey"]["Default"] == "true"
    key = _resource(cfn, "KmsKey")
    assert key["Properties"]["EnableKeyRotation"] is True
    # The PII keyring is unrecoverable without the key, so it must survive stack deletion.
    assert key["DeletionPolicy"] == "Retain"


def test_cfn_kms_key_grants_cloudwatch_logs_scoped_to_this_log_group(cfn: dict[str, Any]) -> None:
    """Without this grant the encrypted log group cannot be created."""
    statements = _resource(cfn, "KmsKey")["Properties"]["KeyPolicy"]["Statement"]
    logs = next(s for s in statements if s["Sid"] == "AllowCloudWatchLogs")
    assert logs["Principal"]["Service"] == {"Fn::Sub": "logs.${AWS::Region}.amazonaws.com"}
    context = logs["Condition"]["ArnEquals"]["kms:EncryptionContext:aws:logs:arn"]
    assert "log-group:/ecs/${AWS::StackName}" in context["Fn::Sub"]


def test_cfn_execution_role_can_decrypt_the_secrets(cfn: dict[str, Any]) -> None:
    """A CMK-encrypted secret is unreadable without kms:Decrypt on the key itself."""
    policy = _resource(cfn, "ExecutionRoleKmsPolicy")
    assert policy["Condition"] == "HasKmsKey"
    statement = policy["Properties"]["PolicyDocument"]["Statement"][0]
    assert statement["Action"] == "kms:Decrypt"
    via = statement["Condition"]["StringEquals"]["kms:ViaService"]
    assert via == {"Fn::Sub": "secretsmanager.${AWS::Region}.amazonaws.com"}


@pytest.mark.parametrize("name", ["PublicSubnet1", "PublicSubnet2"])
def test_cfn_public_subnets_do_not_auto_assign_public_ips(cfn: dict[str, Any], name: str) -> None:
    assert _resource(cfn, name)["Properties"]["MapPublicIpOnLaunch"] is False


def test_cfn_alb_egress_is_scoped_to_the_task_security_group(cfn: dict[str, Any]) -> None:
    egress = _resource(cfn, "AlbSecurityGroup")["Properties"]["SecurityGroupEgress"]
    assert len(egress) == 1
    # Short-form !GetAtt keeps its dotted scalar; only the long form is a two-element list.
    assert egress[0]["DestinationSecurityGroupId"] == {"Fn::GetAtt": "TaskSecurityGroup.GroupId"}
    assert "CidrIp" not in egress[0]


def test_cfn_load_balancer_scheme_is_a_parameter(cfn: dict[str, Any]) -> None:
    scheme = cfn["Parameters"]["LoadBalancerScheme"]
    assert scheme["Default"] == "internet-facing"
    assert set(scheme["AllowedValues"]) == {"internet-facing", "internal"}
    assert _resource(cfn, "LoadBalancer")["Properties"]["Scheme"] == {"Ref": "LoadBalancerScheme"}


# --- Terraform --------------------------------------------------------------


def test_terraform_secrets_and_log_group_take_the_kms_key(tf_main: str) -> None:
    # Two secrets (PII keyring, basic auth) plus the log group.
    assert len(re.findall(r"kms_key_(?:id|arn)\s*=\s*local\.kms_key_arn", tf_main)) == 3


def test_terraform_creates_a_rotating_kms_key_by_default(tf_main: str) -> None:
    key_block = tf_main.split('resource "aws_kms_key" "this"', 1)[1]
    assert "enable_key_rotation     = true" in key_block.split("}", 1)[0] + "}"
    variables = TF_VARIABLES.read_text(encoding="utf-8")
    create_block = variables.split('variable "create_kms_key"', 1)[1]
    assert "default     = true" in create_block


def test_terraform_alb_egress_is_scoped_to_the_task_security_group(tf_main: str) -> None:
    """The ALB SG declares no inline egress; the standalone rule targets only the tasks."""
    alb_block = tf_main.split('resource "aws_security_group" "alb"', 1)[1].split("\nresource ", 1)[0]
    assert "egress {" not in alb_block

    rule = tf_main.split('resource "aws_vpc_security_group_egress_rule" "alb_to_task"', 1)[1]
    rule = rule.split("\nresource ", 1)[0]
    assert "referenced_security_group_id = aws_security_group.task.id" in rule
    assert "cidr_ipv4" not in rule


def test_terraform_load_balancer_scheme_is_a_variable(tf_main: str) -> None:
    assert "internal           = var.internal_lb" in tf_main
    variables = TF_VARIABLES.read_text(encoding="utf-8")
    internal_block = variables.split('variable "internal_lb"', 1)[1]
    assert "default     = false" in internal_block
