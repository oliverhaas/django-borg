import pytest

from django_borg.models import (
    FieldMapping,
    SourceSchema,
    TargetField,
    TargetSchema,
    ValueMapping,
    Vote,
)
from tests import factories


@pytest.mark.django_db
def test_field_mapping_changelist_renders(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=tgt,
    )
    response = admin_client.get("/admin/django_borg/fieldmapping/")
    assert response.status_code == 200
    assert b"Farbe" in response.content


@pytest.mark.django_db
def test_field_mapping_list_display_shows_confidence(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    voter = factories.ReviewerVoterFactory()
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=tgt,
    )
    Vote.objects.create(mapping=fm, voter=voter, agreed_target="color")
    response = admin_client.get("/admin/django_borg/fieldmapping/")
    assert response.status_code == 200
    # current_target rendered after the vote-driven recompute
    assert b"color" in response.content


@pytest.mark.django_db
def test_value_mapping_changelist_renders(admin_client):
    schema = TargetSchema.objects.create(name="Product")
    color = TargetField.objects.create(schema=schema, name="color", is_enum=True)
    ValueMapping.objects.create(target_field=color, source_value="Rot")
    response = admin_client.get("/admin/django_borg/valuemapping/")
    assert response.status_code == 200
    assert b"Rot" in response.content


@pytest.mark.django_db
def test_needs_review_filter_includes_mapping_below_thresholds(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=tgt,
    )
    ai = factories.AiVoterFactory()
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="color")  # 1 ai vote -> below weight threshold
    response = admin_client.get("/admin/django_borg/fieldmapping/?needs_review=yes")
    assert response.status_code == 200
    assert b"Farbe" in response.content


@pytest.mark.django_db
def test_needs_review_filter_excludes_zero_vote_mappings(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    FieldMapping.objects.create(
        source_schema=src,
        source_field="Untouched",
        target_schema=tgt,
    )  # zero votes -> should NOT appear
    response = admin_client.get("/admin/django_borg/fieldmapping/?needs_review=yes")
    assert response.status_code == 200
    assert b"Untouched" not in response.content


@pytest.mark.django_db
def test_needs_review_filter_excludes_graduated_mappings(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Graduated",
        target_schema=tgt,
    )
    reviewer = factories.ReviewerVoterFactory()  # weight 100 -> graduates immediately
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="title")
    response = admin_client.get("/admin/django_borg/fieldmapping/?needs_review=yes")
    assert response.status_code == 200
    assert b"Graduated" not in response.content


@pytest.mark.django_db
def test_conflict_filter_flags_mappings_where_ai_and_human_disagree(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Disputed",
        target_schema=tgt,
    )
    ai = factories.AiVoterFactory()
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="title")
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="color")

    response = admin_client.get("/admin/django_borg/fieldmapping/?conflict=yes")
    assert response.status_code == 200
    assert b"Disputed" in response.content


@pytest.mark.django_db
def test_conflict_filter_excludes_agreement(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Agreed",
        target_schema=tgt,
    )
    ai = factories.AiVoterFactory()
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="title")
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="title")

    response = admin_client.get("/admin/django_borg/fieldmapping/?conflict=yes")
    assert response.status_code == 200
    assert b"Agreed" not in response.content


@pytest.mark.django_db
def test_conflict_filter_excludes_single_voter_kind(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="OnlyAi",
        target_schema=tgt,
    )
    ai = factories.AiVoterFactory()
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="title")

    response = admin_client.get("/admin/django_borg/fieldmapping/?conflict=yes")
    assert response.status_code == 200
    assert b"OnlyAi" not in response.content
