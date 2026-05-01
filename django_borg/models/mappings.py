from django.contrib.contenttypes.fields import GenericRelation
from django.db import models

from django_borg.models.schemas import SourceSchema, TargetField, TargetSchema


class Mapping(models.Model):
    """Abstract base — fields denormalised from votes."""

    current_target = models.CharField(max_length=255, blank=True, default="")
    confidence = models.FloatField(default=0.0)
    total_weight = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    votes = GenericRelation(
        "django_borg.Vote",
        content_type_field="content_type",
        object_id_field="object_id",
        related_query_name="%(class)s",
    )

    class Meta:
        abstract = True


class FieldMapping(Mapping):
    source_schema = models.ForeignKey(
        SourceSchema,
        on_delete=models.CASCADE,
        related_name="field_mappings",
    )
    source_field = models.CharField(max_length=128)
    target_schema = models.ForeignKey(
        TargetSchema,
        on_delete=models.CASCADE,
        related_name="field_mappings",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_schema", "source_field"],
                name="borg_fieldmapping_unique_source",
            ),
        ]

    def __str__(self) -> str:
        target = self.current_target or "?"
        return f"{self.source_schema.name}.{self.source_field} -> {self.target_schema.name}.{target}"


class ValueMapping(Mapping):
    target_field = models.ForeignKey(
        TargetField,
        on_delete=models.CASCADE,
        related_name="value_mappings",
    )
    source_value = models.CharField(max_length=512)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["target_field", "source_value"],
                name="borg_valuemapping_unique_source",
            ),
        ]

    def __str__(self) -> str:
        target = self.current_target or "?"
        return f"{self.target_field}: {self.source_value!r} -> {target!r}"
