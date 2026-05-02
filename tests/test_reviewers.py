import pytest

from django_borg.models import Voter
from django_borg.reviewers import get_or_create_reviewer_voter
from tests import factories


@pytest.mark.django_db
def test_get_or_create_reviewer_voter_creates_on_first_call():
    user = factories.UserFactory(username="alice")
    voter = get_or_create_reviewer_voter(user)
    assert voter.kind == Voter.Kind.HUMAN
    assert voter.identifier == "alice"
    assert voter.weight == 100  # default BORG_REVIEWER_VOTER_WEIGHT


@pytest.mark.django_db
def test_get_or_create_reviewer_voter_is_idempotent():
    user = factories.UserFactory(username="alice")
    a = get_or_create_reviewer_voter(user)
    b = get_or_create_reviewer_voter(user)
    assert a.pk == b.pk
    assert Voter.objects.filter(kind=Voter.Kind.HUMAN, identifier="alice").count() == 1


@pytest.mark.django_db
def test_get_or_create_reviewer_voter_does_not_overwrite_weight():
    user = factories.UserFactory(username="alice")
    voter = get_or_create_reviewer_voter(user)
    voter.weight = 9001  # operator hand-tunes the weight via the admin
    voter.save()

    refetched = get_or_create_reviewer_voter(user)
    assert refetched.weight == 9001
