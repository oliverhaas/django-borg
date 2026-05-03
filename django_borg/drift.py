from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db.models import Max
from django.utils import timezone

from django_borg import conf
from django_borg.models import FieldMapping, ValueMapping, Vote, Voter

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from django.db import models as django_models

    from django_borg.ai import Inferencer


@dataclass
class DriftRunResult:
    field_mappings_revoted: int = 0
    value_mappings_revoted: int = 0
    skipped_recent: int = 0
    skipped_ai_failure: int = 0


class DriftRunner:
    """Re-run AI inference on graduated mappings to detect drift.

    Each AI call is recorded as a normal Vote. The post_save signal recomputes
    confidence on the mapping; existing admin filters surface divergence.
    """

    def __init__(
        self,
        *,
        target_schema: type[django_models.Model],
        ai: Inferencer,
        ai_voter: Voter | None = None,
    ) -> None:
        self.target_model = target_schema
        self.ai = ai
        self.ai_voter = ai_voter or self._ensure_ai_voter()

    @staticmethod
    def _ensure_ai_voter() -> Voter:
        voter, _ = Voter.objects.get_or_create(
            kind=Voter.Kind.AI,
            identifier=conf.ai_voter_identifier(),
            defaults={"weight": conf.ai_voter_weight()},
        )
        return voter

    def run(
        self,
        *,
        source: str | None = None,
        older_than: timedelta | None = None,
        limit: int | None = None,
    ) -> DriftRunResult:
        result = DriftRunResult()
        cutoff = timezone.now() - older_than if older_than is not None else None
        remaining = limit
        target_schema_name = self.target_model.__name__

        remaining = self._drift_field_mappings(
            result,
            target_schema_name,
            source,
            cutoff,
            remaining,
        )
        if source is None and (remaining is None or remaining > 0):
            self._drift_value_mappings(result, target_schema_name, cutoff, remaining)
        return result

    def _drift_field_mappings(
        self,
        result: DriftRunResult,
        target_schema_name: str,
        source: str | None,
        cutoff: datetime | None,
        remaining: int | None,
    ) -> int | None:
        qs = FieldMapping.objects.filter(
            target_schema__name=target_schema_name,
            total_weight__gte=conf.min_weight(),
            confidence__gte=conf.min_confidence(),
        )
        if source is not None:
            qs = qs.filter(source_schema__name=source)

        for mapping in qs:
            if remaining is not None and remaining <= 0:
                return remaining
            if cutoff is not None and self._has_recent_ai_vote(mapping, cutoff):
                result.skipped_recent += 1
                continue
            try:
                target = self.ai.map_field(
                    mapping.source_field,
                    target_schema=target_schema_name,
                )
            except Exception:  # noqa: BLE001
                result.skipped_ai_failure += 1
                continue
            Vote.objects.create(
                mapping=mapping,
                voter=self.ai_voter,
                agreed_target=target,
            )
            result.field_mappings_revoted += 1
            if remaining is not None:
                remaining -= 1
        return remaining

    def _drift_value_mappings(
        self,
        result: DriftRunResult,
        target_schema_name: str,
        cutoff: datetime | None,
        remaining: int | None,
    ) -> None:
        qs = ValueMapping.objects.filter(
            target_field__schema__name=target_schema_name,
            total_weight__gte=conf.min_weight(),
            confidence__gte=conf.min_confidence(),
        ).select_related("target_field")

        for mapping in qs:
            if remaining is not None and remaining <= 0:
                return
            if cutoff is not None and self._has_recent_ai_vote(mapping, cutoff):
                result.skipped_recent += 1
                continue
            try:
                target = self.ai.map_value(
                    mapping.source_value,
                    target_field=mapping.target_field.name,
                )
            except Exception:  # noqa: BLE001
                result.skipped_ai_failure += 1
                continue
            Vote.objects.create(
                mapping=mapping,
                voter=self.ai_voter,
                agreed_target=target,
            )
            result.value_mappings_revoted += 1
            if remaining is not None:
                remaining -= 1

    @staticmethod
    def _has_recent_ai_vote(
        mapping: FieldMapping | ValueMapping,
        cutoff: datetime,
    ) -> bool:
        latest = mapping.votes.filter(voter__kind=Voter.Kind.AI).aggregate(
            latest=Max("created_at"),
        )["latest"]
        return latest is not None and latest >= cutoff
