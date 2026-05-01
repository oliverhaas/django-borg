import pytest
from django.db import IntegrityError

from django_borg.models import (
    FieldMapping,
    SourceField,
    SourceSchema,
    TargetField,
    TargetSchema,
    ValueMapping,
)


@pytest.fixture
def source_schema(db):
    schema = SourceSchema.objects.create(name="acme")
    SourceField.objects.create(schema=schema, name="Farbe")
    return schema


@pytest.fixture
def target_schema(db):
    return TargetSchema.objects.create(name="Product")


@pytest.mark.django_db
def test_field_mapping_defaults_zero_confidence(source_schema, target_schema):
    mapping = FieldMapping.objects.create(
        source_schema=source_schema,
        source_field="Farbe",
        target_schema=target_schema,
    )
    assert mapping.current_target == ""
    assert mapping.confidence == 0.0
    assert mapping.total_weight == 0


@pytest.mark.django_db
def test_field_mapping_str(source_schema, target_schema):
    mapping = FieldMapping.objects.create(
        source_schema=source_schema,
        source_field="Farbe",
        target_schema=target_schema,
    )
    assert str(mapping) == "acme.Farbe -> Product.?"


@pytest.mark.django_db
def test_field_mapping_str_with_resolved_target(source_schema, target_schema):
    mapping = FieldMapping.objects.create(
        source_schema=source_schema,
        source_field="Farbe",
        target_schema=target_schema,
        current_target="color",
        confidence=1.0,
        total_weight=100,
    )
    assert str(mapping) == "acme.Farbe -> Product.color"


@pytest.mark.django_db
def test_field_mapping_unique(source_schema, target_schema):
    FieldMapping.objects.create(
        source_schema=source_schema,
        source_field="Farbe",
        target_schema=target_schema,
    )
    with pytest.raises(IntegrityError):
        FieldMapping.objects.create(
            source_schema=source_schema,
            source_field="Farbe",
            target_schema=target_schema,
        )


@pytest.fixture
def color_field(target_schema):
    return TargetField.objects.create(schema=target_schema, name="color", is_enum=True)


@pytest.mark.django_db
def test_value_mapping_defaults_zero_confidence(color_field):
    mapping = ValueMapping.objects.create(target_field=color_field, source_value="Rot")
    assert mapping.current_target == ""
    assert mapping.confidence == 0.0
    assert mapping.total_weight == 0


@pytest.mark.django_db
def test_value_mapping_str_unresolved(color_field):
    mapping = ValueMapping.objects.create(target_field=color_field, source_value="Rot")
    assert str(mapping) == "Product.color: 'Rot' -> '?'"


@pytest.mark.django_db
def test_value_mapping_str_resolved(color_field):
    mapping = ValueMapping.objects.create(
        target_field=color_field,
        source_value="Rot",
        current_target="red",
    )
    assert str(mapping) == "Product.color: 'Rot' -> 'red'"


@pytest.mark.django_db
def test_value_mapping_unique_per_field_value(color_field):
    ValueMapping.objects.create(target_field=color_field, source_value="Rot")
    with pytest.raises(IntegrityError):
        ValueMapping.objects.create(target_field=color_field, source_value="Rot")
