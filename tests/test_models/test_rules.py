import pytest

from django_borg.models import Rule, TargetField, TargetSchema


@pytest.fixture
def schema(db):
    return TargetSchema.objects.create(name="Product")


@pytest.fixture
def color_field(schema):
    return TargetField.objects.create(schema=schema, name="color")


@pytest.mark.django_db
def test_field_rule_do_exact(schema):
    rule = Rule.objects.create(
        target_schema=schema,
        kind=Rule.Kind.FIELD,
        polarity=Rule.Polarity.DO,
        pattern_type=Rule.PatternType.EXACT,
        source_pattern="Farbe",
        target="color",
    )
    assert rule.polarity == "do"
    assert rule.kind == "field"
    assert str(rule) == "DO field exact 'Farbe' -> 'color'"


@pytest.mark.django_db
def test_value_rule_dont_regex(schema, color_field):
    rule = Rule.objects.create(
        target_schema=schema,
        kind=Rule.Kind.VALUE,
        target_field=color_field,
        polarity=Rule.Polarity.DONT,
        pattern_type=Rule.PatternType.REGEX,
        source_pattern=r"^N/?A$",
        target="",
    )
    assert rule.polarity == "dont"
    assert str(rule) == "DONT value regex '^N/?A$' on Product.color"


@pytest.mark.django_db
def test_rule_polarity_choices():
    assert Rule.Polarity.DO == "do"
    assert Rule.Polarity.DONT == "dont"


@pytest.mark.django_db
def test_rule_kind_choices():
    assert Rule.Kind.FIELD == "field"
    assert Rule.Kind.VALUE == "value"


@pytest.mark.django_db
def test_rule_pattern_type_choices():
    assert Rule.PatternType.EXACT == "exact"
    assert Rule.PatternType.REGEX == "regex"
