from __future__ import annotations

import enum
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django_borg import conf
from django_borg.models.mappings import FieldMapping, ValueMapping
from django_borg.models.rules import Rule
from django_borg.models.votes import Vote

if TYPE_CHECKING:
    from django_borg.ai import Inferencer
    from django_borg.models.schemas import SourceSchema, TargetField, TargetSchema
    from django_borg.models.voters import Voter


class ResolutionSource(enum.StrEnum):
    RULE = "rule"
    MAPPING = "mapping"
    AI = "ai"


EXTRACT_SENTINEL = "__extract__"
"""Reserved target value that routes a source field into the extraction path."""


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


def lookup_field_mapping(
    source_schema: SourceSchema,
    source_field: str,
    target_schema: TargetSchema,
) -> FieldMapping | None:
    return FieldMapping.objects.filter(
        source_schema=source_schema,
        source_field=source_field,
        target_schema=target_schema,
        total_weight__gte=conf.min_weight(),
        confidence__gte=conf.min_confidence(),
    ).first()


def lookup_value_mapping(
    target_field: TargetField,
    source_value: str,
) -> ValueMapping | None:
    return ValueMapping.objects.filter(
        target_field=target_field,
        source_value=source_value,
        total_weight__gte=conf.min_weight(),
        confidence__gte=conf.min_confidence(),
    ).first()


def resolve_field(
    source_schema: SourceSchema,
    source_field: str,
    target_schema: TargetSchema,
    *,
    ai: Inferencer,
    ai_voter: Voter,
) -> Resolution:
    rule = match_field_rule(target_schema, source_field)
    if rule is not None:
        if rule.polarity == Rule.Polarity.DONT:
            return Resolution.block(reason=f"DONT rule on {source_field!r}")
        return Resolution.from_rule(rule.target)

    mapping = lookup_field_mapping(source_schema, source_field, target_schema)
    if mapping is not None:
        return Resolution.from_mapping(mapping.current_target)

    try:
        target = ai.map_field(source_field, target_schema=target_schema.name)
    except Exception as exc:  # noqa: BLE001
        return Resolution.block(reason=f"AI failed for field {source_field!r}: {exc}")

    mapping, _ = FieldMapping.objects.get_or_create(
        source_schema=source_schema,
        source_field=source_field,
        target_schema=target_schema,
    )
    Vote.objects.create(mapping=mapping, voter=ai_voter, agreed_target=target)
    return Resolution.from_ai(target)


def resolve_value(
    target_field: TargetField,
    source_value: str,
    *,
    ai: Inferencer,
    ai_voter: Voter,
) -> Resolution:
    rule = match_value_rule(target_field, source_value)
    if rule is not None:
        if rule.polarity == Rule.Polarity.DONT:
            return Resolution.block(reason=f"DONT rule on value {source_value!r}")
        return Resolution.from_rule(rule.target)

    mapping = lookup_value_mapping(target_field, source_value)
    if mapping is not None:
        return Resolution.from_mapping(mapping.current_target)

    try:
        target = ai.map_value(source_value, target_field=target_field.name)
    except Exception as exc:  # noqa: BLE001
        return Resolution.block(reason=f"AI failed for value {source_value!r}: {exc}")

    mapping, _ = ValueMapping.objects.get_or_create(
        target_field=target_field,
        source_value=source_value,
    )
    Vote.objects.create(mapping=mapping, voter=ai_voter, agreed_target=target)
    return Resolution.from_ai(target)
