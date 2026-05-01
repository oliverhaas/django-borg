import pytest
from django.db import IntegrityError

from django_borg.models import Voter


@pytest.mark.django_db
def test_voter_str_uses_identifier():
    voter = Voter.objects.create(kind=Voter.Kind.AI, identifier="gpt-4o", weight=1)
    assert str(voter) == "gpt-4o (ai, weight=1)"


@pytest.mark.django_db
def test_voter_kind_choices():
    assert Voter.Kind.AI == "ai"
    assert Voter.Kind.HUMAN == "human"


@pytest.mark.django_db
def test_voter_identifier_unique_per_kind():
    Voter.objects.create(kind=Voter.Kind.AI, identifier="gpt-4o", weight=1)
    with pytest.raises(IntegrityError):
        Voter.objects.create(kind=Voter.Kind.AI, identifier="gpt-4o", weight=2)


@pytest.mark.django_db
def test_voter_weight_positive():
    voter = Voter.objects.create(kind=Voter.Kind.HUMAN, identifier="alice", weight=100)
    assert voter.weight == 100
