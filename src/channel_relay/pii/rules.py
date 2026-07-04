"""PII rule models: strict pydantic schema with discriminated actions (§8.1, T2.4).

The wire format is flat (``method`` and its parameters sit at rule level, per §8.1); a
before-validator folds them into a discriminated ``action`` union so each method gets
precise required-parameter validation. Validation is strict and fail-closed: unknown
methods, stray keys, or uncompilable regexes invalidate the whole ruleset — silently
skipping a rule would silently not redact a field. Forward compatibility flows through
``schema_version``, not lax parsing. The rules JSON Schema is generated from these models
(D13), never hand-written.
"""

from __future__ import annotations

import re
from enum import StrEnum
from functools import cached_property
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    field_validator,
    model_validator,
)

SUPPORTED_SCHEMA_MAJOR = 1

# Wire keys that belong to the action, folded out of the flat rule (§8.1 format).
_ACTION_PARAM_KEYS = ("mask_char", "keep_prefix", "replacement")


class PiiType(StrEnum):
    """PII categories (§7). PNR reference, ticket number, itinerary/fare are not PII."""

    PERSON = "person"
    DOB = "dob"
    GENDER = "gender"
    NATIONALITY = "nationality"
    PASSPORT_ID = "passport_id"
    VISA = "visa"
    PHONE = "phone"
    EMAIL = "email"
    ADDRESS = "address"
    PAYMENT = "payment"
    FREQUENT_FLYER = "frequent_flyer"


class EncryptAction(BaseModel):
    """Replace the value with a reversible ``ENC_`` token (the default method)."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["encrypt"] = "encrypt"


class MaskAction(BaseModel):
    """Replace with a one-way mask, optionally keeping a plaintext prefix."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["mask"] = "mask"
    mask_char: str = Field(default="*", min_length=1, max_length=1)
    keep_prefix: int = Field(default=0, ge=0)


class ReplaceAction(BaseModel):
    """Replace with a fixed literal (one-way)."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["replace"] = "replace"
    replacement: str


class RemoveAction(BaseModel):
    """Drop the node's text entirely (one-way)."""

    model_config = ConfigDict(extra="forbid")

    method: Literal["remove"] = "remove"


RuleAction = Annotated[
    EncryptAction | MaskAction | ReplaceAction | RemoveAction,
    Field(discriminator="method"),
]


def _compilable(value: str) -> str:
    try:
        re.compile(value)
    except re.error as exc:
        msg = f"invalid regex {value!r}: {exc}"
        raise ValueError(msg) from exc
    return value


class _BaseRule(BaseModel):
    """Fields common to every rule kind: selection (channel/operation) and location (path)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    channel: str = Field(min_length=1)
    operation: str
    path: str = Field(min_length=1)
    path_type: Literal["xpath", "jsonpath"] = "xpath"
    namespaces: dict[str, str] = Field(
        default_factory=dict,
        description="XPath prefix → namespace URI declarations used by `path`.",
    )

    @field_validator("operation")
    @classmethod
    def _compilable_operation(cls, value: str) -> str:
        return _compilable(value)

    @cached_property
    def operation_re(self) -> re.Pattern[str]:
        """The operation matcher, compiled once at load time (never per request)."""
        return re.compile(self.operation)


class FieldRule(_BaseRule):
    """A single field-redaction rule (``rule_type: field``)."""

    rule_type: Literal["field"] = "field"
    pii_type: PiiType
    action: RuleAction
    ignored_content_patterns: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _fold_flat_action(cls, data: Any) -> Any:
        """Fold the flat wire format (§8.1) into the discriminated ``action`` field.

        All action-parameter keys move with ``method`` so a stray parameter on the wrong
        method is rejected by that action model, never silently dropped.
        """
        if not isinstance(data, dict) or "action" in data:
            return data
        action: dict[str, Any] = {"method": data.pop("method", "encrypt")}
        for key in _ACTION_PARAM_KEYS:
            if key in data:
                action[key] = data.pop(key)
        data["action"] = action
        return data

    @field_validator("ignored_content_patterns")
    @classmethod
    def _compilable_ignored(cls, value: list[str]) -> list[str]:
        for pattern in value:
            _compilable(pattern)
        return value

    @cached_property
    def ignored_re(self) -> tuple[re.Pattern[str], ...]:
        """Compiled ``ignored_content_patterns``."""
        return tuple(re.compile(pattern) for pattern in self.ignored_content_patterns)


class ReferenceRule(_BaseRule):
    """A referential redaction rule (``rule_type: reference``).

    Instead of a value in its own node, this rule redacts occurrences of PII values that
    other ``field`` rules already extracted this pass (grouped by ``source_pii_types``)
    inside the free-text nodes it locates. The action is reversible ``encrypt`` in v1.
    """

    rule_type: Literal["reference"] = "reference"
    source_pii_types: list[PiiType] = Field(
        min_length=1,
        description="pii_type buckets whose collected values are searched for in the target nodes.",
    )
    pii_type: PiiType
    min_match_len: int = Field(default=3, ge=1, description="Collected values shorter than this are skipped.")
    word_boundary: bool = Field(default=True, description="Require non-alphanumeric borders around a match.")
    action: EncryptAction

    @model_validator(mode="before")
    @classmethod
    def _fold_encrypt_action(cls, data: Any) -> Any:
        """Fold the flat ``method`` into ``action``; a non-encrypt method trips ``EncryptAction``."""
        if not isinstance(data, dict) or "action" in data:
            return data
        action: dict[str, Any] = {"method": data.pop("method", "encrypt")}
        for key in _ACTION_PARAM_KEYS:
            if key in data:
                action[key] = data.pop(key)
        data["action"] = action
        return data


def _rule_discriminator(value: Any) -> str:
    """Pick the rule kind from ``rule_type``; absent means the ``field`` default (B/C compat)."""
    if isinstance(value, dict):
        return str(value.get("rule_type", "field"))
    return str(getattr(value, "rule_type", "field"))


Rule = Annotated[
    Annotated[FieldRule, Tag("field")] | Annotated[ReferenceRule, Tag("reference")],
    Discriminator(_rule_discriminator),
]


class RuleSet(BaseModel):
    """A versioned rules document fetched from the API or baked into the image."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str
    rules_version: str = Field(min_length=1)
    rules: list[Rule]

    @field_validator("schema_version")
    @classmethod
    def _compatible_schema(cls, value: str) -> str:
        major = value.split(".", maxsplit=1)[0]
        if not major.isdigit() or int(major) != SUPPORTED_SCHEMA_MAJOR:
            msg = f"schema_version {value!r} unsupported (need major {SUPPORTED_SCHEMA_MAJOR})"
            raise ValueError(msg)
        return value


def generate_rules_json_schema() -> dict[str, Any]:
    """The publishable JSON Schema for rule documents, generated from the models."""
    return RuleSet.model_json_schema()
