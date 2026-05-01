from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.db import models as django_models

from django_borg import conf
from django_borg.models import TargetField, TargetSchema, Voter

if TYPE_CHECKING:
    from django_borg.ai import Inferencer


@dataclass
class AssimilationCost:
    ai_calls: int = 0
    deterministic_hits: int = 0

    def record_ai(self) -> None:
        self.ai_calls += 1

    def record_deterministic(self) -> None:
        self.deterministic_hits += 1


@dataclass
class AssimilationResult:
    product: object
    unresolved: list[str] = field(default_factory=list)
    cost: AssimilationCost = field(default_factory=AssimilationCost)


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
        for model_field in model._meta.get_fields():  # noqa: SLF001
            if not isinstance(model_field, django_models.Field):
                continue
            if model_field.auto_created:
                continue
            TargetField.objects.update_or_create(
                schema=schema,
                name=model_field.name,
                defaults={"is_enum": bool(model_field.choices)},
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
