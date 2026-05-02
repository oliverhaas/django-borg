from typing import TYPE_CHECKING

from django_borg import conf
from django_borg.models import Voter

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser


def get_or_create_reviewer_voter(user: "AbstractBaseUser") -> Voter:
    """Resolve a Django user to a borg Voter (kind=human).

    Auto-creates the Voter on first call with weight ``BORG_REVIEWER_VOTER_WEIGHT``.
    Subsequent calls return the existing Voter without touching its weight, so
    operators can hand-tune weights via the admin without losing them.
    """
    voter, _ = Voter.objects.get_or_create(
        kind=Voter.Kind.HUMAN,
        identifier=user.get_username(),
        defaults={"weight": conf.reviewer_voter_weight()},
    )
    return voter
