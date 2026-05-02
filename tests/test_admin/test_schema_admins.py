import pytest

from django_borg.models import FieldMapping, SourceSchema, TargetField, TargetSchema, Vote
from tests import factories


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


@pytest.mark.django_db
def test_source_schema_detail_shows_field_mapping_count(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    FieldMapping.objects.create(source_schema=src, source_field="A", target_schema=tgt)
    FieldMapping.objects.create(source_schema=src, source_field="B", target_schema=tgt)

    response = admin_client.get(f"/admin/django_borg/sourceschema/{src.pk}/change/")
    assert response.status_code == 200
    # The count is rendered as readonly on the detail page
    assert b"Field mapping count" in response.content
    body = response.content.decode()
    assert ">2<" in body or 'value="2"' in body or "2</" in body


@pytest.mark.django_db
def test_source_schema_detail_distinguishes_graduated_from_pending(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    pending = FieldMapping.objects.create(source_schema=src, source_field="P", target_schema=tgt)
    graduated = FieldMapping.objects.create(source_schema=src, source_field="G", target_schema=tgt)
    reviewer = factories.ReviewerVoterFactory()
    ai = factories.AiVoterFactory()

    Vote.objects.create(mapping=pending, voter=ai, agreed_target="title")  # 1 ai vote -> pending
    Vote.objects.create(mapping=graduated, voter=reviewer, agreed_target="title")  # graduated

    response = admin_client.get(f"/admin/django_borg/sourceschema/{src.pk}/change/")
    assert response.status_code == 200
    body = response.content.decode()
    # Both labels render
    assert "Graduated field mapping count" in body
    assert "Pending field mapping count" in body
