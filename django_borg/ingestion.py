from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models as django_models

from django_borg import conf
from django_borg.models import TargetField, TargetSchema, Voter

if TYPE_CHECKING:
    from django_borg.ai import Inferencer


class SchemaAssimilator:
    """Public ingestion entry point.

    >>> borg = SchemaAssimilator(target_schema=Product, ai=my_inferencer)
    >>> result = borg.assimilate({"Farbe": "Rot"}, source="acme-supplier")
    """

    def __init__(self, *, target_schema: type[django_models.Model], ai: Inferencer) -> None:
        self.target_model = target_schema
        self.ai = ai
        self.target_schema = self._sync_target_schema(target_schema)
        self.ai_voter = self._ensure_ai_voter()

    @staticmethod
    def _sync_target_schema(model: type[django_models.Model]) -> TargetSchema:
        schema, _ = TargetSchema.objects.update_or_create(name=model.__name__)
        for field in model._meta.get_fields():  # noqa: SLF001
            if not isinstance(field, django_models.Field):
                continue
            if field.auto_created:
                continue
            TargetField.objects.update_or_create(
                schema=schema,
                name=field.name,
                defaults={"is_enum": bool(field.choices)},
            )
        return schema

    @staticmethod
    def _ensure_ai_voter() -> Voter:
        voter, _ = Voter.objects.get_or_create(
            kind=Voter.Kind.AI,
            identifier=conf.ai_voter_identifier(),
            defaults={"weight": conf.ai_voter_weight()},
        )
        return voter
