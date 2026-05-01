import pytest
from django.contrib.contenttypes.models import ContentType

from django_borg.models import (
    FieldMapping,
    SourceSchema,
    TargetSchema,
    Vote,
    Voter,
)


@pytest.fixture
def field_mapping(db):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    return FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=tgt,
    )


@pytest.fixture
def ai_voter(db):
    return Voter.objects.create(kind=Voter.Kind.AI, identifier="gpt-4o", weight=1)


@pytest.mark.django_db
def test_vote_links_via_generic_fk(field_mapping, ai_voter):
    vote = Vote.objects.create(
        mapping=field_mapping,
        voter=ai_voter,
        agreed_target="color",
    )
    vote.refresh_from_db()
    assert vote.mapping == field_mapping
    assert vote.voter == ai_voter
    assert vote.agreed_target == "color"
    assert vote.created_at is not None


@pytest.mark.django_db
def test_vote_reverse_relation_from_mapping(field_mapping, ai_voter):
    Vote.objects.create(mapping=field_mapping, voter=ai_voter, agreed_target="color")
    Vote.objects.create(mapping=field_mapping, voter=ai_voter, agreed_target="hue")
    assert field_mapping.votes.count() == 2


@pytest.mark.django_db
def test_vote_str(field_mapping, ai_voter):
    vote = Vote.objects.create(
        mapping=field_mapping,
        voter=ai_voter,
        agreed_target="color",
    )
    assert str(vote) == "gpt-4o votes 'color' (weight=1)"


@pytest.mark.django_db
def test_vote_content_type_set_correctly(field_mapping, ai_voter):
    vote = Vote.objects.create(
        mapping=field_mapping,
        voter=ai_voter,
        agreed_target="color",
    )
    assert vote.content_type == ContentType.objects.get_for_model(FieldMapping)
    assert vote.object_id == field_mapping.pk
