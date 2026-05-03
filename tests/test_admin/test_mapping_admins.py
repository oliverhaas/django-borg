import pytest

from django_borg.models import (
    FieldMapping,
    SourceSchema,
    TargetField,
    TargetSchema,
    ValueMapping,
    Vote,
)
from django_borg.reviewers import get_or_create_reviewer_voter
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


@pytest.mark.django_db
def test_bulk_approve_writes_reviewer_votes(admin_client, admin_user):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=tgt,
    )
    ai = factories.AiVoterFactory()
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="color")
    fm.refresh_from_db()
    assert fm.current_target == "color"

    response = admin_client.post(
        "/admin/django_borg/fieldmapping/",
        {
            "action": "approve_current_target",
            "_selected_action": [str(fm.pk)],
        },
        follow=True,
    )
    assert response.status_code == 200
    fm.refresh_from_db()
    # Reviewer vote (weight 100) added on top of the 1 ai vote -> graduated.
    assert fm.total_weight == 101
    assert fm.current_target == "color"
    # Vote was attributed to the admin user's reviewer voter
    reviewer = get_or_create_reviewer_voter(admin_user)
    assert Vote.objects.filter(voter=reviewer, agreed_target="color").count() == 1


@pytest.mark.django_db
def test_bulk_approve_skips_mappings_without_current_target(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    empty = FieldMapping.objects.create(
        source_schema=src,
        source_field="Empty",
        target_schema=tgt,
    )  # zero votes, current_target == ""

    response = admin_client.post(
        "/admin/django_borg/fieldmapping/",
        {
            "action": "approve_current_target",
            "_selected_action": [str(empty.pk)],
        },
        follow=True,
    )
    assert response.status_code == 200
    empty.refresh_from_db()
    assert empty.total_weight == 0  # no vote written
    # The success message reports the skip count
    messages = [m.message for m in response.context["messages"]]
    assert any("skipped" in m.lower() for m in messages)


@pytest.mark.django_db
def test_bulk_approve_works_on_value_mappings(admin_client, admin_user):
    schema = TargetSchema.objects.create(name="Product")
    color = TargetField.objects.create(schema=schema, name="color", is_enum=True)
    vm = ValueMapping.objects.create(target_field=color, source_value="Rot")
    ai = factories.AiVoterFactory()
    Vote.objects.create(mapping=vm, voter=ai, agreed_target="red")

    admin_client.post(
        "/admin/django_borg/valuemapping/",
        {
            "action": "approve_current_target",
            "_selected_action": [str(vm.pk)],
        },
        follow=True,
    )
    vm.refresh_from_db()
    assert vm.total_weight == 101
    assert vm.current_target == "red"


@pytest.mark.django_db
def test_drift_filter_flags_mapping_with_diverging_latest_ai_vote(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Drifty",
        target_schema=tgt,
    )
    reviewer = factories.ReviewerVoterFactory()
    ai = factories.AiVoterFactory()
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="color")  # current_target="color"
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="hue")  # latest AI disagrees

    response = admin_client.get("/admin/django_borg/fieldmapping/?drift=yes")
    assert response.status_code == 200
    assert b"Drifty" in response.content


@pytest.mark.django_db
def test_drift_filter_excludes_mapping_without_ai_votes(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="NoAi",
        target_schema=tgt,
    )
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="color")

    response = admin_client.get("/admin/django_borg/fieldmapping/?drift=yes")
    assert response.status_code == 200
    assert b"NoAi" not in response.content


@pytest.mark.django_db
def test_drift_filter_excludes_when_latest_ai_agrees(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Stable",
        target_schema=tgt,
    )
    reviewer = factories.ReviewerVoterFactory()
    ai = factories.AiVoterFactory()
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="color")
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="color")  # AI agrees

    response = admin_client.get("/admin/django_borg/fieldmapping/?drift=yes")
    assert response.status_code == 200
    assert b"Stable" not in response.content
