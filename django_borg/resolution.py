from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django_borg.models.rules import Rule

if TYPE_CHECKING:
    from django_borg.models.schemas import TargetField, TargetSchema


class ResolutionSource(enum.StrEnum):
    RULE = "rule"
    MAPPING = "mapping"
    AI = "ai"


@dataclass(frozen=True, slots=True)
class Resolution:
    target: str | None
    source: ResolutionSource | None
    blocked: bool = False
    reason: str = ""

    @classmethod
    def from_rule(cls, target: str) -> Resolution:
        return cls(target=target, source=ResolutionSource.RULE)

    @classmethod
    def from_mapping(cls, target: str) -> Resolution:
        return cls(target=target, source=ResolutionSource.MAPPING)

    @classmethod
    def from_ai(cls, target: str) -> Resolution:
        return cls(target=target, source=ResolutionSource.AI)

    @classmethod
    def block(cls, reason: str = "") -> Resolution:
        return cls(target=None, source=None, blocked=True, reason=reason)


def _matches(rule: Rule, value: str) -> bool:
    if rule.pattern_type == Rule.PatternType.EXACT:
        return rule.source_pattern == value
    return re.fullmatch(rule.source_pattern, value) is not None


def match_field_rule(target_schema: TargetSchema, source_field: str) -> Rule | None:
    rules = Rule.objects.filter(target_schema=target_schema, kind=Rule.Kind.FIELD)
    for rule in rules:
        if _matches(rule, source_field):
            return rule
    return None


def match_value_rule(target_field: TargetField, source_value: str) -> Rule | None:
    rules = Rule.objects.filter(
        target_schema=target_field.schema,
        kind=Rule.Kind.VALUE,
        target_field=target_field,
    )
    for rule in rules:
        if _matches(rule, source_value):
            return rule
    return None
