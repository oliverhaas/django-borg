import pytest
from django.db import IntegrityError

from django_borg.models import TargetField, TargetSchema


@pytest.mark.django_db
def test_target_schema_str_uses_name():
    schema = TargetSchema.objects.create(name="Product")
    assert str(schema) == "Product"


@pytest.mark.django_db
def test_target_schema_name_unique():
    TargetSchema.objects.create(name="Product")
    with pytest.raises(IntegrityError):
        TargetSchema.objects.create(name="Product")


@pytest.mark.django_db
def test_target_field_belongs_to_schema():
    schema = TargetSchema.objects.create(name="Product")
    field = TargetField.objects.create(schema=schema, name="color", is_enum=True)
    assert str(field) == "Product.color"
    assert field.is_enum is True


@pytest.mark.django_db
def test_target_field_unique_per_schema():
    schema = TargetSchema.objects.create(name="Product")
    TargetField.objects.create(schema=schema, name="color")
    with pytest.raises(IntegrityError):
        TargetField.objects.create(schema=schema, name="color")


@pytest.mark.django_db
def test_target_field_default_not_enum():
    schema = TargetSchema.objects.create(name="Product")
    field = TargetField.objects.create(schema=schema, name="title")
    assert field.is_enum is False
