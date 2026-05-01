from django.db import models


class Voter(models.Model):
    class Kind(models.TextChoices):
        AI = "ai", "AI"
        HUMAN = "human", "Human"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    identifier = models.CharField(max_length=255)
    weight = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "identifier"],
                name="borg_voter_unique_identifier_per_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.identifier} ({self.kind}, weight={self.weight})"
