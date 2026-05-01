import pytest
from django.db import IntegrityError

from django_borg.models import SourceField, SourceSchema, TargetField, TargetSchema


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


@pytest.mark.django_db
def test_source_schema_str_uses_name():
    schema = SourceSchema.objects.create(name="acme-supplier")
    assert str(schema) == "acme-supplier"


@pytest.mark.django_db
def test_source_schema_name_unique():
    SourceSchema.objects.create(name="acme-supplier")
    with pytest.raises(IntegrityError):
        SourceSchema.objects.create(name="acme-supplier")


@pytest.mark.django_db
def test_source_field_belongs_to_schema():
    schema = SourceSchema.objects.create(name="acme-supplier")
    field = SourceField.objects.create(schema=schema, name="Farbe")
    assert str(field) == "acme-supplier.Farbe"


@pytest.mark.django_db
def test_source_field_unique_per_schema():
    schema = SourceSchema.objects.create(name="acme-supplier")
    SourceField.objects.create(schema=schema, name="Farbe")
    with pytest.raises(IntegrityError):
        SourceField.objects.create(schema=schema, name="Farbe")
