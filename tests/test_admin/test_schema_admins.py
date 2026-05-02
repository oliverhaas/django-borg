import pytest

from django_borg.models import SourceSchema, TargetField, TargetSchema


@pytest.mark.django_db
def test_target_schema_changelist_renders(admin_client):
    TargetSchema.objects.create(name="Product")
    response = admin_client.get("/admin/django_borg/targetschema/")
    assert response.status_code == 200
    assert b"Product" in response.content


@pytest.mark.django_db
def test_target_schema_detail_shows_field_inline(admin_client):
    schema = TargetSchema.objects.create(name="Product")
    TargetField.objects.create(schema=schema, name="color", is_enum=True)
    response = admin_client.get(f"/admin/django_borg/targetschema/{schema.pk}/change/")
    assert response.status_code == 200
    assert b"color" in response.content


@pytest.mark.django_db
def test_source_schema_changelist_renders(admin_client):
    SourceSchema.objects.create(name="acme-supplier")
    response = admin_client.get("/admin/django_borg/sourceschema/")
    assert response.status_code == 200
    assert b"acme-supplier" in response.content


@pytest.mark.django_db
def test_target_schema_search(admin_client):
    """RuleAdmin's autocomplete_fields requires search_fields here."""
    TargetSchema.objects.create(name="Product")
    response = admin_client.get("/admin/django_borg/targetschema/?q=Product")
    assert response.status_code == 200
    assert b"Product" in response.content
