from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django_borg import conf
from django_borg.models import FieldMapping, Vote, Voter

if TYPE_CHECKING:
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

    def run(self) -> DriftRunResult:
        result = DriftRunResult()
        min_weight = conf.min_weight()
        min_confidence = conf.min_confidence()

        candidates = FieldMapping.objects.filter(
            target_schema__name=self.target_model.__name__,
            total_weight__gte=min_weight,
            confidence__gte=min_confidence,
        )
        for mapping in candidates:
            try:
                target = self.ai.map_field(
                    mapping.source_field,
                    target_schema=self.target_model.__name__,
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

        return result
