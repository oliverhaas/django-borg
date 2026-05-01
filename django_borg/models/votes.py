from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from django_borg.models.voters import Voter


class Vote(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    mapping = GenericForeignKey("content_type", "object_id")

    voter = models.ForeignKey(Voter, on_delete=models.PROTECT, related_name="votes")
    agreed_target = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="borg_vote_target_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.voter.identifier} votes {self.agreed_target!r} (weight={self.voter.weight})"
