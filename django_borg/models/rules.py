from django.db import models

from django_borg.models.schemas import TargetField, TargetSchema


class Rule(models.Model):
    class Kind(models.TextChoices):
        FIELD = "field", "Field"
        VALUE = "value", "Value"

    class Polarity(models.TextChoices):
        DO = "do", "Do"
        DONT = "dont", "Don't"

    class PatternType(models.TextChoices):
        EXACT = "exact", "Exact"
        REGEX = "regex", "Regex"

    target_schema = models.ForeignKey(
        TargetSchema,
        on_delete=models.CASCADE,
        related_name="rules",
    )
    kind = models.CharField(max_length=8, choices=Kind.choices)
    target_field = models.ForeignKey(
        TargetField,
        on_delete=models.CASCADE,
        related_name="rules",
        null=True,
        blank=True,
        help_text="Required for value rules; null for field rules.",
    )

    polarity = models.CharField(max_length=8, choices=Polarity.choices)
    pattern_type = models.CharField(max_length=8, choices=PatternType.choices)
    source_pattern = models.CharField(max_length=512)
    target = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        polarity = self.polarity.upper()
        if self.kind == self.Kind.FIELD:
            return f"{polarity} field {self.pattern_type} {self.source_pattern!r} -> {self.target!r}"
        scope = f"{self.target_schema.name}.{self.target_field.name}" if self.target_field else "?"
        return f"{polarity} value {self.pattern_type} {self.source_pattern!r} on {scope}"
