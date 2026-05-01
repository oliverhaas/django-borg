import pytest

from django_borg.models import Rule, TargetSchema
from django_borg.resolution import (
    Resolution,
    ResolutionSource,
    match_field_rule,
)
from tests import factories


@pytest.mark.django_db
def test_no_rules_returns_none():
    schema = TargetSchema.objects.create(name="Product")
    assert match_field_rule(schema, "Farbe") is None


@pytest.mark.django_db
def test_exact_do_rule_matches():
    schema = TargetSchema.objects.create(name="Product")
    factories.FieldRuleFactory(
        target_schema=schema,
        source_pattern="Farbe",
        target="color",
    )
    rule = match_field_rule(schema, "Farbe")
    assert rule is not None
    assert rule.target == "color"


@pytest.mark.django_db
def test_exact_rule_does_not_match_different_input():
    schema = TargetSchema.objects.create(name="Product")
    factories.FieldRuleFactory(
        target_schema=schema,
        source_pattern="Farbe",
        target="color",
    )
    assert match_field_rule(schema, "Color") is None


@pytest.mark.django_db
def test_regex_rule_matches():
    schema = TargetSchema.objects.create(name="Product")
    factories.FieldRuleFactory(
        target_schema=schema,
        pattern_type=Rule.PatternType.REGEX,
        source_pattern=r"^Farbe.*$",
        target="color",
    )
    rule = match_field_rule(schema, "Farbe (DE)")
    assert rule is not None


@pytest.mark.django_db
def test_dont_rule_returned_with_dont_polarity():
    schema = TargetSchema.objects.create(name="Product")
    factories.FieldRuleFactory(
        target_schema=schema,
        source_pattern="Farbe",
        polarity=Rule.Polarity.DONT,
        target="",
    )
    rule = match_field_rule(schema, "Farbe")
    assert rule.polarity == Rule.Polarity.DONT


def test_resolution_dataclass_carries_source_and_target():
    res = Resolution(target="color", source=ResolutionSource.RULE)
    assert res.target == "color"
    assert res.source == ResolutionSource.RULE
    assert res.blocked is False


def test_resolution_blocked():
    res = Resolution.block(reason="DONT rule")
    assert res.blocked is True
    assert res.target is None
    assert res.reason == "DONT rule"
