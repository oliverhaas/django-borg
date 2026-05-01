import pytest

from django_borg.confidence import recompute_confidence
from django_borg.models import (
    FieldMapping,
    SourceSchema,
    TargetSchema,
    Vote,
    Voter,
)


@pytest.fixture
def mapping(db):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    return FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=tgt,
    )


@pytest.fixture
def ai(db):
    return Voter.objects.create(kind=Voter.Kind.AI, identifier="ai", weight=1)


@pytest.fixture
def reviewer(db):
    return Voter.objects.create(kind=Voter.Kind.HUMAN, identifier="alice", weight=100)


@pytest.mark.django_db
def test_no_votes_yields_zero_confidence(mapping):
    recompute_confidence(mapping)
    assert mapping.current_target == ""
    assert mapping.confidence == 0.0
    assert mapping.total_weight == 0


@pytest.mark.django_db
def test_unanimous_ai_votes(mapping, ai):
    for _ in range(5):
        Vote.objects.create(mapping=mapping, voter=ai, agreed_target="color")
    mapping.refresh_from_db()
    assert mapping.current_target == "color"
    assert mapping.confidence == pytest.approx(1.0)
    assert mapping.total_weight == 5


@pytest.mark.django_db
def test_split_votes_weighted(mapping, ai, reviewer):
    Vote.objects.create(mapping=mapping, voter=ai, agreed_target="hue")
    Vote.objects.create(mapping=mapping, voter=reviewer, agreed_target="color")
    mapping.refresh_from_db()
    assert mapping.current_target == "color"  # reviewer outweighs ai
    assert mapping.confidence == pytest.approx(100 / 101)
    assert mapping.total_weight == 101


@pytest.mark.django_db
def test_signal_fires_on_vote_create(mapping, ai):
    Vote.objects.create(mapping=mapping, voter=ai, agreed_target="color")
    mapping.refresh_from_db()
    assert mapping.current_target == "color"
    assert mapping.total_weight == 1


@pytest.mark.django_db
def test_signal_recomputes_on_each_vote(mapping, ai, reviewer):
    Vote.objects.create(mapping=mapping, voter=ai, agreed_target="hue")
    mapping.refresh_from_db()
    assert mapping.current_target == "hue"
    Vote.objects.create(mapping=mapping, voter=reviewer, agreed_target="color")
    mapping.refresh_from_db()
    assert mapping.current_target == "color"
