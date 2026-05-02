import pytest

from django_borg.models import TargetSchema, Vote, Voter
from tests import factories


@pytest.mark.django_db
def test_voter_changelist_renders(admin_client):
    factories.AiVoterFactory()
    response = admin_client.get("/admin/django_borg/voter/")
    assert response.status_code == 200
    assert b"ai-test" in response.content


@pytest.mark.django_db
def test_voter_can_be_added_via_admin(admin_client):
    response = admin_client.post(
        "/admin/django_borg/voter/add/",
        {
            "kind": "human",
            "identifier": "bob",
            "weight": "50",
        },
    )
    assert response.status_code in (302, 200)
    assert Voter.objects.filter(kind="human", identifier="bob", weight=50).exists()


@pytest.mark.django_db
def test_rule_changelist_renders(admin_client):
    schema = TargetSchema.objects.create(name="Product")
    factories.FieldRuleFactory(
        target_schema=schema,
        source_pattern="Farbe",
        target="color",
    )
    response = admin_client.get("/admin/django_borg/rule/")
    assert response.status_code == 200
    assert b"Farbe" in response.content


@pytest.mark.django_db
def test_rule_kind_filter_present(admin_client):
    response = admin_client.get("/admin/django_borg/rule/")
    assert response.status_code == 200
    # The list_filter renders the choice labels in the right sidebar.
    assert b"By kind" in response.content


@pytest.mark.django_db
def test_vote_changelist_renders(admin_client):
    src = TargetSchema.objects.create(name="Product")
    voter = factories.AiVoterFactory()
    mapping = factories.FieldMappingFactory(target_schema=src, source_field="Farbe")
    Vote.objects.create(mapping=mapping, voter=voter, agreed_target="color")
    response = admin_client.get("/admin/django_borg/vote/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_vote_admin_disallows_change(admin_client):
    voter = factories.AiVoterFactory()
    mapping = factories.FieldMappingFactory()
    vote = Vote.objects.create(mapping=mapping, voter=voter, agreed_target="color")
    response = admin_client.get(f"/admin/django_borg/vote/{vote.pk}/change/")
    assert response.status_code == 200
    assert b'name="_save"' not in response.content


@pytest.mark.django_db
def test_vote_admin_disallows_delete(admin_client):
    voter = factories.AiVoterFactory()
    mapping = factories.FieldMappingFactory()
    vote = Vote.objects.create(mapping=mapping, voter=voter, agreed_target="color")
    response = admin_client.get(f"/admin/django_borg/vote/{vote.pk}/delete/")
    assert response.status_code == 403
