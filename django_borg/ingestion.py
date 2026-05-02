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
    extraction_calls: int = 0

    def record_ai(self) -> None:
        self.ai_calls += 1

    def record_deterministic(self) -> None:
        self.deterministic_hits += 1

    def record_extraction(self) -> None:
        self.extraction_calls += 1


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

    def assimilate(self, raw_item: dict[str, str], *, source: str) -> AssimilationResult:
        from django_borg.models.schemas import SourceField, SourceSchema  # noqa: PLC0415
        from django_borg.resolution import resolve_field  # noqa: PLC0415

        source_schema, _ = SourceSchema.objects.get_or_create(name=source)
        cost = AssimilationCost()
        unresolved: list[str] = []
        mapped: dict[str, str] = {}

        for src_field_name, src_value in raw_item.items():
            SourceField.objects.get_or_create(schema=source_schema, name=src_field_name)

            field_res = resolve_field(
                source_schema,
                src_field_name,
                self.target_schema,
                ai=self.ai,
                ai_voter=self.ai_voter,
            )
            self._record_cost(field_res, cost)

            if field_res.blocked or field_res.target is None:
                unresolved.append(src_field_name)
                continue

            target_field_name = field_res.target
            try:
                target_field = TargetField.objects.get(
                    schema=self.target_schema,
                    name=target_field_name,
                )
            except TargetField.DoesNotExist:
                unresolved.append(src_field_name)
                continue

            value = self._resolve_value_or_raw(target_field, src_value, cost)
            if value is None:
                unresolved.append(src_field_name)
                continue
            mapped[target_field_name] = value

        return AssimilationResult(
            product=self.target_model(**mapped),
            unresolved=unresolved,
            cost=cost,
        )

    def _resolve_value_or_raw(
        self,
        target_field: TargetField,
        src_value: str,
        cost: AssimilationCost,
    ) -> str | None:
        if not src_value:
            return src_value
        if not target_field.is_enum:
            return src_value
        from django_borg.resolution import resolve_value  # noqa: PLC0415

        res = resolve_value(target_field, src_value, ai=self.ai, ai_voter=self.ai_voter)
        self._record_cost(res, cost)
        if res.blocked or res.target is None:
            return None
        return res.target

    @staticmethod
    def _record_cost(resolution: object, cost: AssimilationCost) -> None:
        from django_borg.resolution import ResolutionSource  # noqa: PLC0415

        source = getattr(resolution, "source", None)
        if source == ResolutionSource.AI:
            cost.record_ai()
        elif source in (ResolutionSource.MAPPING, ResolutionSource.RULE):
            cost.record_deterministic()
