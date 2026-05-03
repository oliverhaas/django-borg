# django-borg Drift Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-run AI inference on already-graduated mappings on demand. Disagreements are recorded as fresh AI Votes — the existing post_save signal recomputes confidence, the existing NeedsReview/Conflict filters surface the divergence, and a new Drift admin filter highlights "the most recent AI vote disagrees with the current target."

**Architecture:** Ship a programmatic `DriftRunner` class that consumers wire into their own Celery beat / cron / management command. Operating shape mirrors `SchemaAssimilator` — accept the target Django model, an `Inferencer`, and an optional ai voter; expose a single `run()` method with `source` / `older_than` / `limit` filters and return a `DriftRunResult` dataclass. No new models or signals — drift is computed from the existing append-only Vote log.

**Tech Stack:** Django 5.2+, Python 3.12+, the existing django-borg core engine + extraction + admin. No new dependencies.

---

## What this plan does NOT deliver

- **No management command.** Operating cadence and Inferencer wiring are consumer concerns; the programmatic API is the slice that ships. (A canned `borg_drift_run` would force a `BORG_DRIFT_INFERENCER_FACTORY` setting plus dynamic import; defer that until consumers tell us what they actually want.)
- **No drift on `Extraction`** — extraction blobs are usually unique, so re-running the AI on the same blob doesn't tell us anything new. Drift applies to FieldMapping and ValueMapping.
- **No automatic scheduling / Celery integration.** Consumers schedule their own jobs.
- **No drift-specific Vote subclass or "drift event" log.** Each AI re-vote is just a normal Vote — its `created_at` and the existing `current_target` mismatch are sufficient to detect divergence.

## File layout impacted

```
django_borg/
  drift.py             # NEW — DriftRunner, DriftRunResult
  admin.py             # +DriftFilter (one filter, applied to both mapping admins)
  __init__.py          # +DriftRunner, DriftRunResult exports

tests/
  test_drift.py        # NEW — DriftRunner behaviour
  test_admin/
    test_mapping_admins.py   # +DriftFilter tests
  test_public_api.py   # +exports
README.md              # +Drift detection section
```

## Key design decisions (locked in this plan)

- **DriftRunner is parameterised at construction**, not at call time, so a consumer can hold one runner and trigger it from cron / Celery / a management command of their own. Constructor takes `target_schema=` (Django model), `ai=` (Inferencer), and optional `ai_voter=`. If `ai_voter` is `None`, falls back to the same auto-created `BORG_AI_VOTER_IDENTIFIER` voter that `SchemaAssimilator` uses.
- **`run(*, source=None, older_than=None, limit=None) -> DriftRunResult`.** Iterates over **graduated** field mappings (and value mappings), calls the AI, records each result as a Vote. The existing post_save signal handles confidence recompute. Returns a stats dataclass.
  - `source: str | None` — restricts field mappings to that supplier (matches `SourceSchema.name`). ValueMappings are supplier-agnostic by design — when `source` is set, value mappings are skipped entirely (drift on ValueMapping happens only on a global run).
  - `older_than: timedelta | None` — skip a candidate mapping if **the latest AI vote on it is younger than `now - older_than`**. Mappings with zero AI votes always proceed (a graduated-by-reviewers mapping deserves an AI sanity-check).
  - `limit: int | None` — cap total iterations across both kinds. Field mappings consumed first, then value mappings.
- **"Graduated"** is the same definition used by `lookup_field_mapping` / `lookup_value_mapping`: `total_weight >= conf.min_weight() AND confidence >= conf.min_confidence()`.
- **AI failure is recoverable.** If `ai.map_field` / `ai.map_value` raises, the runner increments `skipped_ai_failure`, records nothing, and moves on. A drift run never crashes a batch.
- **Drift detection in the admin** is computed from votes, not stored. A mapping is drift-flagged iff it has at least one AI vote AND the **most recent** AI vote's `agreed_target` differs from the mapping's `current_target`. Implemented as `DriftFilter` (`SimpleListFilter`), Python-side query in the same shape as `ConflictFilter`.
- **No new Voter records.** DriftRunner's `_ensure_ai_voter` mirrors `SchemaAssimilator._ensure_ai_voter` and is shared via a small helper rather than duplicated.

## Settings

No new settings. DriftRunner uses the existing `BORG_AI_VOTER_IDENTIFIER` and `BORG_AI_VOTER_WEIGHT` for its default AI voter.

---

## Task 1: `DriftRunner` for FieldMapping (basic loop, no filters)

**Files:**
- Create: `django_borg/drift.py`
- Create: `tests/test_drift.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_drift.py`:

```python
import pytest
from testapp.models import Product

from django_borg.ai import FakeInferencer
from django_borg.drift import DriftRunner, DriftRunResult
from django_borg.models import FieldMapping, SourceSchema, TargetSchema, Vote
from tests import factories


@pytest.fixture
def graduated_field_mapping(db):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src, source_field="Farbe", target_schema=tgt,
    )
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="color")
    fm.refresh_from_db()
    assert fm.confidence >= 0.9
    assert fm.total_weight >= 5
    return fm


@pytest.mark.django_db
def test_drift_runner_revotes_graduated_field_mapping(graduated_field_mapping):
    ai = FakeInferencer(field_map={"Farbe": "color"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run()
    assert isinstance(result, DriftRunResult)
    assert result.field_mappings_revoted == 1
    # AI vote was recorded.
    assert graduated_field_mapping.votes.filter(voter__kind="ai").count() == 1


@pytest.mark.django_db
def test_drift_runner_skips_ungraduated_field_mapping(db):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    FieldMapping.objects.create(
        source_schema=src, source_field="Untouched", target_schema=tgt,
    )  # zero votes -> not graduated
    ai = FakeInferencer(field_map={"Untouched": "title"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run()
    assert result.field_mappings_revoted == 0
    assert ai.calls == []


@pytest.mark.django_db
def test_drift_runner_records_ai_failure(graduated_field_mapping):
    ai = FakeInferencer()  # empty -> raises LookupError
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run()
    assert result.field_mappings_revoted == 0
    assert result.skipped_ai_failure == 1


@pytest.mark.django_db
def test_drift_runner_disagreement_drops_confidence(graduated_field_mapping):
    """Initial state: 1 reviewer vote (weight 100) for 'color', confidence=1.0.
    Drift run produces an AI vote for 'hue' (weight 1) -> confidence drops to 100/101.
    """
    ai = FakeInferencer(field_map={"Farbe": "hue"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    runner.run()
    graduated_field_mapping.refresh_from_db()
    assert graduated_field_mapping.current_target == "color"  # reviewer still wins
    assert graduated_field_mapping.confidence == pytest.approx(100 / 101)
```

- [ ] **Step 2: Run — expect ImportError**

Run: `uv run pytest tests/test_drift.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'django_borg.drift'`.

- [ ] **Step 3: Write `django_borg/drift.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import models as django_models

from django_borg import conf
from django_borg.models import FieldMapping, Vote, Voter

if TYPE_CHECKING:
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
                mapping=mapping, voter=self.ai_voter, agreed_target=target,
            )
            result.field_mappings_revoted += 1

        return result
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_drift.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add django_borg/drift.py tests/test_drift.py
git commit -m "feat: add DriftRunner for re-voting graduated field mappings"
```

---

## Task 2: DriftRunner for ValueMapping

**Files:**
- Modify: `django_borg/drift.py`
- Modify: `tests/test_drift.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_drift.py`:

```python
from django_borg.models import TargetField, ValueMapping


@pytest.fixture
def graduated_value_mapping(db):
    schema = TargetSchema.objects.create(name="Product")
    color = TargetField.objects.create(schema=schema, name="color", is_enum=True)
    vm = ValueMapping.objects.create(target_field=color, source_value="Rot")
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=vm, voter=reviewer, agreed_target="red")
    vm.refresh_from_db()
    return vm


@pytest.mark.django_db
def test_drift_runner_revotes_graduated_value_mapping(graduated_value_mapping):
    ai = FakeInferencer(value_map={("color", "Rot"): "red"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run()
    assert result.value_mappings_revoted == 1
    assert graduated_value_mapping.votes.filter(voter__kind="ai").count() == 1


@pytest.mark.django_db
def test_drift_runner_skips_ungraduated_value_mapping(db):
    schema = TargetSchema.objects.create(name="Product")
    color = TargetField.objects.create(schema=schema, name="color", is_enum=True)
    ValueMapping.objects.create(target_field=color, source_value="Rot")  # zero votes
    ai = FakeInferencer(value_map={("color", "Rot"): "red"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run()
    assert result.value_mappings_revoted == 0


@pytest.mark.django_db
def test_drift_runner_value_ai_failure_increments_skipped(graduated_value_mapping):
    ai = FakeInferencer()  # raises on map_value
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run()
    assert result.value_mappings_revoted == 0
    assert result.skipped_ai_failure == 1


@pytest.mark.django_db
def test_drift_runner_only_drifts_value_mappings_under_target_schema(db):
    """Two TargetSchemas; runner targeting Product must skip the 'Other' schema."""
    schema_other = TargetSchema.objects.create(name="Other")
    color_other = TargetField.objects.create(schema=schema_other, name="color", is_enum=True)
    vm_other = ValueMapping.objects.create(target_field=color_other, source_value="Rot")
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=vm_other, voter=reviewer, agreed_target="red")

    ai = FakeInferencer(value_map={("color", "Rot"): "red"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run()
    assert result.value_mappings_revoted == 0  # Product has no value mappings
```

- [ ] **Step 2: Run — expect failures**

Run: `uv run pytest tests/test_drift.py -v`
Expected: 4 new failures (`value_mappings_revoted` is always 0; AI is never called).

- [ ] **Step 3: Extend `DriftRunner.run` for value mappings**

Edit `django_borg/drift.py`. Replace the `run` method with:

```python
    def run(self) -> DriftRunResult:
        result = DriftRunResult()
        min_weight = conf.min_weight()
        min_confidence = conf.min_confidence()
        target_schema_name = self.target_model.__name__

        field_candidates = FieldMapping.objects.filter(
            target_schema__name=target_schema_name,
            total_weight__gte=min_weight,
            confidence__gte=min_confidence,
        )
        for mapping in field_candidates:
            try:
                target = self.ai.map_field(
                    mapping.source_field,
                    target_schema=target_schema_name,
                )
            except Exception:  # noqa: BLE001
                result.skipped_ai_failure += 1
                continue
            Vote.objects.create(
                mapping=mapping, voter=self.ai_voter, agreed_target=target,
            )
            result.field_mappings_revoted += 1

        value_candidates = ValueMapping.objects.filter(
            target_field__schema__name=target_schema_name,
            total_weight__gte=min_weight,
            confidence__gte=min_confidence,
        ).select_related("target_field")
        for mapping in value_candidates:
            try:
                target = self.ai.map_value(
                    mapping.source_value,
                    target_field=mapping.target_field.name,
                )
            except Exception:  # noqa: BLE001
                result.skipped_ai_failure += 1
                continue
            Vote.objects.create(
                mapping=mapping, voter=self.ai_voter, agreed_target=target,
            )
            result.value_mappings_revoted += 1

        return result
```

Add `ValueMapping` to the imports near the top:

```python
from django_borg.models import FieldMapping, ValueMapping, Vote, Voter
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_drift.py -v`
Expected: 8 passed (4 from Task 1 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add django_borg/drift.py tests/test_drift.py
git commit -m "feat: DriftRunner re-votes graduated value mappings"
```

---

## Task 3: DriftRunner filters — `older_than`, `source`, `limit`

**Files:**
- Modify: `django_borg/drift.py`
- Modify: `tests/test_drift.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_drift.py`:

```python
from datetime import timedelta

from django.utils import timezone


@pytest.mark.django_db
def test_drift_runner_older_than_skips_recent_ai_votes(graduated_field_mapping):
    ai_voter = factories.AiVoterFactory()
    Vote.objects.create(mapping=graduated_field_mapping, voter=ai_voter, agreed_target="color")
    # Most recent ai vote is "now" -- older_than=1h should skip it.
    ai = FakeInferencer(field_map={"Farbe": "color"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run(older_than=timedelta(hours=1))
    assert result.skipped_recent == 1
    assert result.field_mappings_revoted == 0


@pytest.mark.django_db
def test_drift_runner_older_than_runs_when_no_ai_vote(graduated_field_mapping):
    """No prior AI vote -> always run regardless of older_than."""
    ai = FakeInferencer(field_map={"Farbe": "color"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run(older_than=timedelta(days=365))
    assert result.field_mappings_revoted == 1


@pytest.mark.django_db
def test_drift_runner_older_than_runs_when_ai_vote_is_old(graduated_field_mapping):
    ai_voter = factories.AiVoterFactory()
    old_vote = Vote.objects.create(
        mapping=graduated_field_mapping, voter=ai_voter, agreed_target="color",
    )
    # Backdate the vote.
    Vote.objects.filter(pk=old_vote.pk).update(
        created_at=timezone.now() - timedelta(days=10),
    )
    ai = FakeInferencer(field_map={"Farbe": "color"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run(older_than=timedelta(days=1))
    assert result.field_mappings_revoted == 1


@pytest.mark.django_db
def test_drift_runner_source_filter_restricts_to_supplier(graduated_field_mapping):
    other_src = SourceSchema.objects.create(name="other")
    tgt = TargetSchema.objects.get(name="Product")
    other_fm = FieldMapping.objects.create(
        source_schema=other_src, source_field="Farbe", target_schema=tgt,
    )
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=other_fm, voter=reviewer, agreed_target="color")

    ai = FakeInferencer(field_map={"Farbe": "color"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run(source="acme")
    # Only the "acme" mapping is drifted; "other" stays untouched.
    assert result.field_mappings_revoted == 1
    other_fm.refresh_from_db()
    assert other_fm.votes.filter(voter__kind="ai").count() == 0


@pytest.mark.django_db
def test_drift_runner_source_skips_value_mappings(graduated_value_mapping):
    """ValueMappings are supplier-agnostic; passing source= disables them."""
    ai = FakeInferencer(value_map={("color", "Rot"): "red"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run(source="acme")
    assert result.value_mappings_revoted == 0


@pytest.mark.django_db
def test_drift_runner_limit_caps_total_iterations(db):
    """Three graduated field mappings; limit=2 stops after the second."""
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    reviewer = factories.ReviewerVoterFactory()
    for name in ["A", "B", "C"]:
        fm = FieldMapping.objects.create(
            source_schema=src, source_field=name, target_schema=tgt,
        )
        Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="title")

    ai = FakeInferencer(field_map={"A": "title", "B": "title", "C": "title"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run(limit=2)
    assert result.field_mappings_revoted == 2
```

- [ ] **Step 2: Run — expect failures**

Run: `uv run pytest tests/test_drift.py -v`
Expected: 6 new failures (`run()` ignores its kwargs because they don't exist yet).

- [ ] **Step 3: Replace `DriftRunner.run` with the filtered version**

Edit `django_borg/drift.py`. At the top, ensure imports include `datetime`/`timedelta`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from django.db.models import Max
from django.utils import timezone

from django_borg import conf
from django_borg.models import FieldMapping, ValueMapping, Vote, Voter

if TYPE_CHECKING:
    from django_borg.ai import Inferencer
```

Replace the `run` method with:

```python
    def run(
        self,
        *,
        source: str | None = None,
        older_than: timedelta | None = None,
        limit: int | None = None,
    ) -> DriftRunResult:
        result = DriftRunResult()
        min_weight = conf.min_weight()
        min_confidence = conf.min_confidence()
        target_schema_name = self.target_model.__name__
        cutoff = timezone.now() - older_than if older_than is not None else None
        remaining = limit

        field_qs = FieldMapping.objects.filter(
            target_schema__name=target_schema_name,
            total_weight__gte=min_weight,
            confidence__gte=min_confidence,
        )
        if source is not None:
            field_qs = field_qs.filter(source_schema__name=source)

        for mapping in field_qs:
            if remaining is not None and remaining <= 0:
                return result
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
                mapping=mapping, voter=self.ai_voter, agreed_target=target,
            )
            result.field_mappings_revoted += 1
            if remaining is not None:
                remaining -= 1

        if source is not None:
            return result  # ValueMappings are supplier-agnostic; skip when scoped.

        value_qs = ValueMapping.objects.filter(
            target_field__schema__name=target_schema_name,
            total_weight__gte=min_weight,
            confidence__gte=min_confidence,
        ).select_related("target_field")

        for mapping in value_qs:
            if remaining is not None and remaining <= 0:
                return result
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
                mapping=mapping, voter=self.ai_voter, agreed_target=target,
            )
            result.value_mappings_revoted += 1
            if remaining is not None:
                remaining -= 1

        return result

    @staticmethod
    def _has_recent_ai_vote(
        mapping: FieldMapping | ValueMapping,
        cutoff: datetime,
    ) -> bool:
        latest = mapping.votes.filter(voter__kind=Voter.Kind.AI).aggregate(
            latest=Max("created_at"),
        )["latest"]
        return latest is not None and latest >= cutoff
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_drift.py -v`
Expected: 14 passed (8 prior + 6 new).

- [ ] **Step 5: Commit**

```bash
git add django_borg/drift.py tests/test_drift.py
git commit -m "feat: DriftRunner filters by source, age, and total iteration limit"
```

---

## Task 4: `DriftFilter` admin filter

**Files:**
- Modify: `django_borg/admin.py`
- Modify: `tests/test_admin/test_mapping_admins.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_admin/test_mapping_admins.py`:

```python
@pytest.mark.django_db
def test_drift_filter_flags_mapping_with_diverging_latest_ai_vote(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src, source_field="Drifty", target_schema=tgt,
    )
    reviewer = factories.ReviewerVoterFactory()
    ai = factories.AiVoterFactory()
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="color")  # current_target="color"
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="hue")  # latest AI disagrees

    response = admin_client.get("/admin/django_borg/fieldmapping/?drift=yes")
    assert response.status_code == 200
    assert b"Drifty" in response.content


@pytest.mark.django_db
def test_drift_filter_excludes_mapping_without_ai_votes(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src, source_field="NoAi", target_schema=tgt,
    )
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="color")

    response = admin_client.get("/admin/django_borg/fieldmapping/?drift=yes")
    assert response.status_code == 200
    assert b"NoAi" not in response.content


@pytest.mark.django_db
def test_drift_filter_excludes_when_latest_ai_agrees(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src, source_field="Stable", target_schema=tgt,
    )
    reviewer = factories.ReviewerVoterFactory()
    ai = factories.AiVoterFactory()
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="color")
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="color")  # AI agrees

    response = admin_client.get("/admin/django_borg/fieldmapping/?drift=yes")
    assert response.status_code == 200
    assert b"Stable" not in response.content
```

- [ ] **Step 2: Run — expect failures**

Run: `uv run pytest tests/test_admin/test_mapping_admins.py -v`
Expected: 3 new failures (admin redirects to `?e=1` because `drift` isn't a valid filter).

- [ ] **Step 3: Add `DriftFilter` to `django_borg/admin.py`**

Append immediately after the existing `ConflictFilter` class:

```python
class DriftFilter(admin.SimpleListFilter):
    """Latest AI vote on the mapping disagrees with its current_target."""

    title = "drift"
    parameter_name = "drift"

    def lookups(
        self,
        request: "HttpRequest",  # noqa: ARG002
        model_admin: admin.ModelAdmin,  # noqa: ARG002
    ) -> list[tuple[str, str]]:
        return [("yes", "Latest AI vote disagrees")]

    def queryset(
        self,
        request: "HttpRequest",  # noqa: ARG002
        qs: "QuerySet",
    ) -> "QuerySet":
        if self.value() != "yes":
            return qs
        ct = ContentType.objects.get_for_model(qs.model)
        latest_ai_per_mapping: dict[int, str] = {}
        ai_votes = (
            Vote.objects.filter(
                content_type=ct,
                object_id__in=qs.values_list("pk", flat=True),
                voter__kind=Voter.Kind.AI,
            )
            .order_by("object_id", "-created_at")
            .values("object_id", "agreed_target")
        )
        for v in ai_votes:
            latest_ai_per_mapping.setdefault(v["object_id"], v["agreed_target"])

        # current_target by pk
        current_targets: dict[int, str] = dict(
            qs.values_list("pk", "current_target"),
        )
        drift_pks = [
            pk
            for pk, latest_ai in latest_ai_per_mapping.items()
            if latest_ai != current_targets.get(pk, "")
        ]
        return qs.filter(pk__in=drift_pks)
```

Wire it into both mapping admins. Update `FieldMappingAdmin.list_filter`:

```python
    list_filter = (NeedsReviewFilter, ConflictFilter, DriftFilter, "source_schema", "target_schema")
```

Update `ValueMappingAdmin.list_filter`:

```python
    list_filter = (NeedsReviewFilter, ConflictFilter, DriftFilter, "target_field__schema")
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_admin/test_mapping_admins.py -v`
Expected: 15 passed (12 prior + 3 new).

- [ ] **Step 5: Commit**

```bash
git add django_borg/admin.py tests/test_admin/test_mapping_admins.py
git commit -m "feat: Drift admin filter highlights mappings with diverging latest AI vote"
```

---

## Task 5: Public API + lint/type/README

**Files:**
- Modify: `django_borg/__init__.py`
- Modify: `tests/test_public_api.py`
- Modify: `README.md`

- [ ] **Step 1: Append failing exports test**

Append to `tests/test_public_api.py`:

```python
from django_borg import DriftRunner, DriftRunResult


def test_drift_exports():
    assert DriftRunner is not None
    assert DriftRunResult is not None
```

- [ ] **Step 2: Run — expect ImportError**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: FAIL — `cannot import name 'DriftRunner'`.

- [ ] **Step 3: Add lazy exports**

Edit `django_borg/__init__.py`. Update `__all__`:

```python
__all__ = [
    "EXTRACT_SENTINEL",
    "AssimilationCost",
    "AssimilationResult",
    "DriftRunResult",
    "DriftRunner",
    "FakeInferencer",
    "Inferencer",
    "Resolution",
    "ResolutionSource",
    "SchemaAssimilator",
]
```

Update `_LAZY_MODULES`:

```python
_LAZY_MODULES = {
    "AssimilationCost": "django_borg.ingestion",
    "AssimilationResult": "django_borg.ingestion",
    "SchemaAssimilator": "django_borg.ingestion",
    "FakeInferencer": "django_borg.ai",
    "Inferencer": "django_borg.ai",
    "Resolution": "django_borg.resolution",
    "ResolutionSource": "django_borg.resolution",
    "EXTRACT_SENTINEL": "django_borg.resolution",
    "DriftRunner": "django_borg.drift",
    "DriftRunResult": "django_borg.drift",
}
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run ruff, format, mypy, and full suite**

Run each in order; fix any errors in place before moving on.

```bash
uv run ruff check django_borg tests
uv run ruff format --check django_borg tests
uv run mypy django_borg
uv run pytest -q
```

Expected: all clean. Pytest: 142 passed (124 prior + 14 drift + 3 admin drift + 1 public api new export). Coverage ≥ 90%.

- [ ] **Step 6: Append README section**

Insert in `README.md` immediately before the `## Documentation` line:

```markdown
## Drift detection

Re-run AI inference on already-graduated mappings to catch supplier or model
drift:

```python
from django_borg import DriftRunner

runner = DriftRunner(target_schema=Product, ai=ai)
result = runner.run(
    source="acme-supplier",        # restrict field mappings to one supplier (optional)
    older_than=timedelta(days=30), # skip mappings whose latest AI vote is fresh (optional)
    limit=100,                      # cap total iterations (optional)
)
# result.field_mappings_revoted, result.value_mappings_revoted,
# result.skipped_recent, result.skipped_ai_failure
```

Each AI re-vote is a normal Vote — the post_save signal recomputes confidence,
and any divergence shows up in the **Drift** admin filter on FieldMapping /
ValueMapping changelists ("latest AI vote disagrees with current target"). When
human-weight votes still keep a mapping graduated despite AI drift, the drift
filter still flags it for review.

Schedule the runner from a Celery beat task, a `cron` job, or your own
management command — the package keeps the moving parts to a minimum and
leaves cadence to the consumer.
```

- [ ] **Step 7: Commit**

```bash
git add django_borg/__init__.py tests/test_public_api.py README.md
git commit -m "feat: export DriftRunner and document drift detection"
```

---

## Self-review checklist (run after Task 5)

- [ ] Periodic AI review runs — `DriftRunner.run()` (Tasks 1–3).
- [ ] Drift event surfaces in the queue — existing NeedsReviewFilter (when reviewer weight is insufficient) plus new DriftFilter (when reviewer weight masks the divergence) (Task 4).
- [ ] Append-only Vote justifies the log over a confidence float — drift detection reads `created_at` to find the latest AI opinion (Tasks 3, 4).
- [ ] No new models, no new signals, no new migrations.
- [ ] No placeholders.
- [ ] Type/name consistency: `DriftRunner`, `DriftRunResult`, `field_mappings_revoted`, `value_mappings_revoted`, `skipped_recent`, `skipped_ai_failure`, `DriftFilter`.

---

## Out of scope (still — separate plans)

- **Management command** (`borg_drift_run`) with `BORG_DRIFT_INFERENCER_FACTORY` setting.
- **Reference Pydantic AI / Instructor adapter** — Plan 5.
- **Drift on `Extraction`** — extraction blobs are usually unique, so re-running the AI on the same blob doesn't yield new signal. Revisit if extraction caching ever ships.
