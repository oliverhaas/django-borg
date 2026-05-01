from typing import Any

from django.db.models.signals import post_save
from django.dispatch import receiver

from django_borg.confidence import recompute_confidence
from django_borg.models.votes import Vote


@receiver(post_save, sender=Vote, dispatch_uid="borg_vote_post_save_recompute")
def _recompute_on_vote_save(
    sender: type[Vote],  # noqa: ARG001
    instance: Vote,
    created: bool,  # noqa: FBT001
    **kwargs: Any,  # noqa: ANN401, ARG001
) -> None:
    if not created:
        return
    mapping = instance.mapping
    if mapping is not None:
        recompute_confidence(mapping)
