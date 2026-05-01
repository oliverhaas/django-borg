import pytest
from testapp.models import Product

from django_borg.ai import FakeInferencer
from django_borg.ingestion import AssimilationCost, AssimilationResult, SchemaAssimilator
from django_borg.models import TargetField, TargetSchema, Voter


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
