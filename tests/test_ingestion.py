import pytest
from testapp.models import Product

from django_borg.ai import FakeInferencer
from django_borg.ingestion import AssimilationCost, AssimilationResult, SchemaAssimilator
from django_borg.models import (
    FieldMapping,
    Rule,
    SourceSchema,
    TargetField,
    TargetSchema,
    ValueMapping,
    Vote,
    Voter,
)
from tests import factories


@pytest.mark.django_db
def test_init_creates_target_schema_record():
    SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    assert TargetSchema.objects.filter(name="Product").exists()


@pytest.mark.django_db
def test_init_creates_target_fields_for_concrete_columns():
    SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    schema = TargetSchema.objects.get(name="Product")
    names = set(schema.fields.values_list("name", flat=True))
    # 'id' is auto and must be skipped; explicit fields are present.
    assert names == {"title", "color", "size"}


@pytest.mark.django_db
def test_init_marks_choice_fields_as_enum():
    SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    schema = TargetSchema.objects.get(name="Product")
    title = TargetField.objects.get(schema=schema, name="title")
    color = TargetField.objects.get(schema=schema, name="color")
    assert title.is_enum is False
    assert color.is_enum is True


@pytest.mark.django_db
def test_init_creates_default_ai_voter():
    SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    assert Voter.objects.filter(kind=Voter.Kind.AI, identifier="ai").exists()


@pytest.mark.django_db
def test_reinit_is_idempotent():
    SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    assert TargetSchema.objects.filter(name="Product").count() == 1
    assert TargetField.objects.filter(schema__name="Product").count() == 3


def test_assimilation_cost_arithmetic():
    cost = AssimilationCost()
    cost.record_ai()
    cost.record_ai()
    cost.record_deterministic()
    assert cost.ai_calls == 2
    assert cost.deterministic_hits == 1


def test_assimilation_result_carries_product_and_unresolved():
    result = AssimilationResult(
        product=object(),
        unresolved=["mystery_field"],
        cost=AssimilationCost(),
    )
    assert result.unresolved == ["mystery_field"]


@pytest.fixture
def borg(db):
    ai = FakeInferencer(
        field_map={"Farbe": "color", "Titel": "title", "Größe": "size"},
        value_map={
            ("color", "Rot"): "red",
            ("size", "M"): "M",
        },
    )
    return SchemaAssimilator(target_schema=Product, ai=ai)


@pytest.mark.django_db
def test_assimilate_returns_unsaved_product_instance(borg):
    result = borg.assimilate(
        {"Titel": "T-Shirt", "Farbe": "Rot", "Größe": "M"},
        source="acme",
    )
    assert isinstance(result.product, Product)
    assert result.product.pk is None  # unsaved
    assert result.product.title == "T-Shirt"
    assert result.product.color == "red"
    assert result.product.size == "M"


@pytest.mark.django_db
def test_assimilate_creates_source_schema_on_first_use(borg):
    borg.assimilate({"Farbe": "Rot"}, source="acme")
    assert SourceSchema.objects.filter(name="acme").exists()


@pytest.mark.django_db
def test_assimilate_records_cost_for_first_run(borg):
    result = borg.assimilate(
        {"Titel": "T-Shirt", "Farbe": "Rot", "Größe": "M"},
        source="acme",
    )
    # 3 field calls + 2 value calls (title is not enum, no value lookup) = 5 AI calls
    assert result.cost.ai_calls == 5
    assert result.cost.deterministic_hits == 0


@pytest.mark.django_db
def test_assimilate_uses_deterministic_path_after_graduation(borg):
    src = SourceSchema.objects.create(name="acme")
    schema = TargetSchema.objects.get(name="Product")
    color = TargetField.objects.get(schema=schema, name="color")

    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=schema,
    )
    vm = ValueMapping.objects.create(target_field=color, source_value="Rot")
    reviewer = factories.ReviewerVoterFactory()

    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="color")
    Vote.objects.create(mapping=vm, voter=reviewer, agreed_target="red")

    result = borg.assimilate({"Farbe": "Rot"}, source="acme")
    assert result.product.color == "red"
    assert result.cost.ai_calls == 0
    assert result.cost.deterministic_hits == 2  # field + value


@pytest.mark.django_db
def test_assimilate_reports_unresolved_when_ai_fails():
    ai = FakeInferencer()  # empty -> AI raises LookupError
    borg = SchemaAssimilator(target_schema=Product, ai=ai)
    result = borg.assimilate({"Mystery": "x"}, source="acme")
    assert result.unresolved == ["Mystery"]
    assert result.product.title == ""  # default


@pytest.mark.django_db
def test_assimilate_skips_blank_source_values(borg):
    result = borg.assimilate({"Titel": "T-Shirt", "Farbe": ""}, source="acme")
    # 'Farbe' is blank -> skip value resolution; field still mapped but value stays blank.
    assert result.product.color == ""
    assert result.product.title == "T-Shirt"


@pytest.mark.django_db
def test_assimilate_blocked_field_skips_assignment(borg):
    schema = TargetSchema.objects.get(name="Product")
    factories.FieldRuleFactory(
        target_schema=schema,
        source_pattern="internal_id",
        polarity=Rule.Polarity.DONT,
        target="",
    )
    result = borg.assimilate({"internal_id": "123", "Titel": "X"}, source="acme")
    assert result.product.title == "X"
    assert "internal_id" in result.unresolved


def test_assimilation_cost_records_extraction():
    cost = AssimilationCost()
    cost.record_extraction()
    cost.record_extraction()
    assert cost.extraction_calls == 2
    assert cost.ai_calls == 0  # extraction call counter is independent
