import pytest
from django.test import override_settings

from django_borg.ai import FakeInferencer
from django_borg.models import (
    FieldMapping,
    Rule,
    SourceSchema,
    TargetField,
    TargetSchema,
    ValueMapping,
    Vote,
)
from django_borg.resolution import (
    Resolution,
    ResolutionSource,
    lookup_field_mapping,
    match_field_rule,
    resolve_field,
    resolve_value,
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


@pytest.mark.django_db
def test_lookup_returns_none_when_no_mapping():
    src = SourceSchema.objects.create(name="acme")
    schema = TargetSchema.objects.create(name="Product")
    assert lookup_field_mapping(src, "Farbe", schema) is None


@pytest.mark.django_db
def test_lookup_returns_none_when_below_thresholds():
    src = SourceSchema.objects.create(name="acme")
    schema = TargetSchema.objects.create(name="Product")
    mapping = FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=schema,
    )
    ai = factories.AiVoterFactory()
    Vote.objects.create(mapping=mapping, voter=ai, agreed_target="color")
    # Only 1 weight -> below default BORG_MIN_WEIGHT (5).
    assert lookup_field_mapping(src, "Farbe", schema) is None


@pytest.mark.django_db
def test_lookup_returns_mapping_when_above_thresholds():
    src = SourceSchema.objects.create(name="acme")
    schema = TargetSchema.objects.create(name="Product")
    mapping = FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=schema,
    )
    reviewer = factories.ReviewerVoterFactory()  # weight=100
    Vote.objects.create(mapping=mapping, voter=reviewer, agreed_target="color")
    found = lookup_field_mapping(src, "Farbe", schema)
    assert found == mapping


@pytest.mark.django_db
@override_settings(BORG_MIN_CONFIDENCE=0.6)
def test_lookup_respects_overridden_confidence():
    src = SourceSchema.objects.create(name="acme")
    schema = TargetSchema.objects.create(name="Product")
    mapping = FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=schema,
    )
    ai = factories.AiVoterFactory()
    # 7 votes for 'color', 3 for 'hue' -> 0.7 confidence, weight 10.
    for _ in range(7):
        Vote.objects.create(mapping=mapping, voter=ai, agreed_target="color")
    for _ in range(3):
        Vote.objects.create(mapping=mapping, voter=ai, agreed_target="hue")
    found = lookup_field_mapping(src, "Farbe", schema)
    assert found == mapping


@pytest.mark.django_db
def test_resolve_field_returns_rule_target_when_rule_matches():
    schema = TargetSchema.objects.create(name="Product")
    src = SourceSchema.objects.create(name="acme")
    factories.FieldRuleFactory(
        target_schema=schema,
        source_pattern="Farbe",
        target="color",
    )
    ai = FakeInferencer()
    ai_voter = factories.AiVoterFactory()
    res = resolve_field(src, "Farbe", schema, ai=ai, ai_voter=ai_voter)
    assert res.source == ResolutionSource.RULE
    assert res.target == "color"
    # Rule wins, no AI call recorded.
    assert ai.calls == []


@pytest.mark.django_db
def test_resolve_field_blocked_by_dont_rule():
    schema = TargetSchema.objects.create(name="Product")
    src = SourceSchema.objects.create(name="acme")
    factories.FieldRuleFactory(
        target_schema=schema,
        source_pattern="internal_id",
        polarity=Rule.Polarity.DONT,
        target="",
    )
    ai = FakeInferencer()
    ai_voter = factories.AiVoterFactory()
    res = resolve_field(src, "internal_id", schema, ai=ai, ai_voter=ai_voter)
    assert res.blocked is True
    assert ai.calls == []


@pytest.mark.django_db
def test_resolve_field_returns_mapping_when_high_confidence():
    schema = TargetSchema.objects.create(name="Product")
    src = SourceSchema.objects.create(name="acme")
    mapping = FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=schema,
    )
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=mapping, voter=reviewer, agreed_target="color")
    ai = FakeInferencer()
    ai_voter = factories.AiVoterFactory()
    res = resolve_field(src, "Farbe", schema, ai=ai, ai_voter=ai_voter)
    assert res.source == ResolutionSource.MAPPING
    assert res.target == "color"
    assert ai.calls == []


@pytest.mark.django_db
def test_resolve_field_falls_through_to_ai_and_records_vote():
    schema = TargetSchema.objects.create(name="Product")
    src = SourceSchema.objects.create(name="acme")
    ai = FakeInferencer(field_map={"Farbe": "color"})
    ai_voter = factories.AiVoterFactory()
    res = resolve_field(src, "Farbe", schema, ai=ai, ai_voter=ai_voter)
    assert res.source == ResolutionSource.AI
    assert res.target == "color"
    # Vote recorded against an auto-created mapping
    mapping = FieldMapping.objects.get(source_schema=src, source_field="Farbe")
    assert mapping.votes.count() == 1
    assert mapping.votes.first().agreed_target == "color"


@pytest.mark.django_db
def test_resolve_field_ai_failure_returns_blocked():
    schema = TargetSchema.objects.create(name="Product")
    src = SourceSchema.objects.create(name="acme")
    ai = FakeInferencer()  # empty -> raises LookupError
    ai_voter = factories.AiVoterFactory()
    res = resolve_field(src, "Mystery", schema, ai=ai, ai_voter=ai_voter)
    assert res.blocked is True
    assert "Mystery" in res.reason


@pytest.mark.django_db
def test_resolve_value_uses_value_rule():
    schema = TargetSchema.objects.create(name="Product")
    color = TargetField.objects.create(schema=schema, name="color", is_enum=True)
    factories.ValueRuleFactory(
        target_schema=schema,
        target_field=color,
        source_pattern="Rot",
        target="red",
    )
    ai = FakeInferencer()
    res = resolve_value(color, "Rot", ai=ai, ai_voter=factories.AiVoterFactory())
    assert res.source == ResolutionSource.RULE
    assert res.target == "red"


@pytest.mark.django_db
def test_resolve_value_uses_high_confidence_mapping():
    schema = TargetSchema.objects.create(name="Product")
    color = TargetField.objects.create(schema=schema, name="color", is_enum=True)
    mapping = ValueMapping.objects.create(target_field=color, source_value="Rot")
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=mapping, voter=reviewer, agreed_target="red")
    ai = FakeInferencer()
    res = resolve_value(color, "Rot", ai=ai, ai_voter=factories.AiVoterFactory())
    assert res.source == ResolutionSource.MAPPING
    assert res.target == "red"


@pytest.mark.django_db
def test_resolve_value_falls_through_to_ai_and_records_vote():
    schema = TargetSchema.objects.create(name="Product")
    color = TargetField.objects.create(schema=schema, name="color", is_enum=True)
    ai = FakeInferencer(value_map={("color", "Rot"): "red"})
    res = resolve_value(color, "Rot", ai=ai, ai_voter=factories.AiVoterFactory())
    assert res.source == ResolutionSource.AI
    assert res.target == "red"
    mapping = ValueMapping.objects.get(target_field=color, source_value="Rot")
    assert mapping.votes.count() == 1


@pytest.mark.django_db
def test_resolve_value_ai_failure_returns_blocked():
    schema = TargetSchema.objects.create(name="Product")
    color = TargetField.objects.create(schema=schema, name="color", is_enum=True)
    ai = FakeInferencer()
    res = resolve_value(color, "Rot", ai=ai, ai_voter=factories.AiVoterFactory())
    assert res.blocked is True
