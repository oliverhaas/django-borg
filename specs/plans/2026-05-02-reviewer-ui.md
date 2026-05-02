# django-borg Reviewer UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every borg model curatable through Django's admin: triage queues for low-confidence mappings, conflict surfacing where AI and human votes disagree, a bulk-approve action that writes high-weight reviewer votes, and per-supplier coverage stats.

**Architecture:** Stay inside Django's admin — no SPA, no HTMX. Each ModelAdmin is small and focused. The reviewer's identity is mapped from `request.user` to a `Voter(kind=human, identifier=username)` row via a single helper, weighted by `BORG_REVIEWER_VOTER_WEIGHT` (default 100). Bulk approval becomes "create one reviewer-weight Vote per selected mapping for its `current_target`," which the existing post_save signal turns into a graduated mapping.

**Tech Stack:** Django 5.2+ admin, `django.contrib.auth`, pytest-django (admin client), the existing django-borg core engine + extraction.

---

## What this plan does NOT deliver

- **Live preview of rule matches** against existing data — useful but complex; deferred until rules are actually being authored at scale.
- **Drift indicators** — needs the drift detection plumbing (Plan 4).
- **Bulk reject / bulk lock** — only bulk approve in v0.1. Reject is doable per-mapping by adding a Vote with a different `agreed_target`; lock is "give an admin's Voter a very high weight," done via the Voter admin.
- **Real-time updates / HTMX** — admin's stock page reload is fine.
- **Custom admin theming** — stock Django admin styles only.

## File layout impacted

```
django_borg/
  reviewers.py         # NEW — get_or_create_reviewer_voter(user), reviewer_voter_weight
  conf.py              # +reviewer_voter_weight()
  admin.py             # NEW — all ModelAdmin classes, filters, and bulk actions

tests/
  conftest.py          # +admin_user / admin_client fixtures
  factories.py         # +UserFactory
  settings/base.py     # +admin/auth/sessions/messages, MIDDLEWARE, TEMPLATES, STATIC_URL
  settings/urls.py     # +admin.site.urls
  test_admin/          # NEW
    __init__.py
    test_simple_admins.py     # Voter, Rule, Vote
    test_schema_admins.py     # TargetSchema, SourceSchema, inlines, per-supplier stats
    test_mapping_admins.py    # FieldMapping/ValueMapping list, filters, bulk approve
  test_reviewers.py    # NEW — reviewer voter helper
README.md              # +Admin section
```

## Key design decisions (locked in this plan)

- **One `admin.py`** with everything (ModelAdmins, filters, actions). If it grows past ~400 lines we split — for v0.1 it stays under that.
- **Reviewer voter is per-Django-user**, identified by `username`. Auto-created on first review action, weight = `BORG_REVIEWER_VOTER_WEIGHT` (default 100). Helper is `get_or_create_reviewer_voter(user)` in `django_borg.reviewers`. The weight on an existing reviewer Voter is **not** updated on subsequent calls — operators can adjust weights manually via the Voter admin.
- **Vote is append-only** in the admin too: `VoteAdmin` allows add (so reviewers can hand-craft a vote with any `agreed_target`) but forbids change/delete.
- **NeedsReview filter** = `total_weight > 0 AND (confidence < BORG_MIN_CONFIDENCE OR total_weight < BORG_MIN_WEIGHT)`. Rationale: a mapping with zero votes is just unsurveyed, not "needs review." A mapping that's **graduated** (above both thresholds) doesn't either. Everything in between is the queue.
- **Conflict filter** = mapping has at least one AI vote and at least one human vote, and the set of AI-voted targets differs from the set of human-voted targets. Computed Python-side (loop over relevant Vote rows once, build per-mapping kind→targets map, intersect at the end). Acceptable cost: admins are low-traffic and the dataset is bounded by what's visible in the changelist.
- **Bulk approve writes one reviewer-weight Vote per selected mapping** with `agreed_target=mapping.current_target`. Mappings with empty `current_target` are skipped and counted into the success message ("Approved N, skipped M with no current target").
- **Per-supplier stats** on `SourceSchemaAdmin`: three computed readonly fields — `field_mapping_count`, `graduated_field_mapping_count`, `pending_field_mapping_count`. ValueMapping is target-field-scoped, not supplier-scoped, so it's excluded from supplier stats (mentioning this explicitly because it's a tempting addition).
- **Admin URLs** mounted at `/admin/` in the test URL conf. Production consumers wire admin themselves; this plan only ensures the package's admin module loads correctly when registered.
- **Test admin client uses `Client.force_login()`**. No password handling.

## Settings (read via `django_borg.conf`)

| setting | default | meaning |
|---|---|---|
| `BORG_REVIEWER_VOTER_WEIGHT` | `100` | weight assigned to auto-created Django-user reviewer voters |

(plus the existing settings from Plan 1)

---

## Task 1: Admin test infrastructure + reviewer voter helper

**Files:**
- Modify: `tests/settings/base.py`
- Modify: `tests/settings/urls.py`
- Modify: `tests/factories.py`
- Modify: `tests/conftest.py`
- Modify: `django_borg/conf.py`
- Create: `django_borg/reviewers.py`
- Create: `tests/test_reviewers.py`

- [ ] **Step 1: Expand `tests/settings/base.py` for admin**

Replace the body of `tests/settings/base.py` with:

```python
SECRET_KEY = "test-secret-key"

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django_borg",
    "testapp",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    },
}

MIGRATION_MODULES = {"testapp": None}

STATIC_URL = "/static/"

USE_TZ = True

ROOT_URLCONF = "settings.urls"

BORG_MIN_WEIGHT = 5
BORG_MIN_CONFIDENCE = 0.9
BORG_AI_VOTER_IDENTIFIER = "ai"
BORG_AI_VOTER_WEIGHT = 1
BORG_REVIEWER_VOTER_WEIGHT = 100
```

- [ ] **Step 2: Mount admin URLs**

Replace `tests/settings/urls.py`:

```python
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
]
```

- [ ] **Step 3: Add `UserFactory`**

Append to `tests/factories.py`:

```python
from django.contrib.auth import get_user_model


class UserFactory(DjangoModelFactory):
    class Meta:
        model = get_user_model()
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda u: f"{u.username}@example.test")
    is_staff = True
    is_superuser = True
```

- [ ] **Step 4: Add admin client fixtures to `tests/conftest.py`**

Replace `tests/conftest.py`:

```python
"""Pytest configuration."""

import pytest
from django.test import Client

from tests import factories


@pytest.fixture
def ai_voter(db):
    return factories.AiVoterFactory()


@pytest.fixture
def reviewer_voter(db):
    return factories.ReviewerVoterFactory()


@pytest.fixture
def admin_user(db):
    return factories.UserFactory()


@pytest.fixture
def admin_client(admin_user):
    client = Client()
    client.force_login(admin_user)
    return client
```

- [ ] **Step 5: Add `reviewer_voter_weight()` to `conf.py`**

Append to `django_borg/conf.py`:

```python
def reviewer_voter_weight() -> int:
    return int(getattr(settings, "BORG_REVIEWER_VOTER_WEIGHT", 100))
```

- [ ] **Step 6: Write failing reviewer-helper test**

Create `tests/test_reviewers.py`:

```python
import pytest

from django_borg.models import Voter
from django_borg.reviewers import get_or_create_reviewer_voter
from tests import factories


@pytest.mark.django_db
def test_get_or_create_reviewer_voter_creates_on_first_call():
    user = factories.UserFactory(username="alice")
    voter = get_or_create_reviewer_voter(user)
    assert voter.kind == Voter.Kind.HUMAN
    assert voter.identifier == "alice"
    assert voter.weight == 100  # default BORG_REVIEWER_VOTER_WEIGHT


@pytest.mark.django_db
def test_get_or_create_reviewer_voter_is_idempotent():
    user = factories.UserFactory(username="alice")
    a = get_or_create_reviewer_voter(user)
    b = get_or_create_reviewer_voter(user)
    assert a.pk == b.pk
    assert Voter.objects.filter(kind=Voter.Kind.HUMAN, identifier="alice").count() == 1


@pytest.mark.django_db
def test_get_or_create_reviewer_voter_does_not_overwrite_weight():
    user = factories.UserFactory(username="alice")
    voter = get_or_create_reviewer_voter(user)
    voter.weight = 9001  # operator hand-tunes the weight via the admin
    voter.save()

    refetched = get_or_create_reviewer_voter(user)
    assert refetched.weight == 9001
```

- [ ] **Step 7: Run — expect ImportError**

Run: `uv run pytest tests/test_reviewers.py -v`
Expected: FAIL — `cannot import name 'get_or_create_reviewer_voter'`.

- [ ] **Step 8: Write `django_borg/reviewers.py`**

```python
from typing import TYPE_CHECKING

from django_borg import conf
from django_borg.models import Voter

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser


def get_or_create_reviewer_voter(user: "AbstractBaseUser") -> Voter:
    """Resolve a Django user to a borg Voter (kind=human).

    Auto-creates the Voter on first call with weight ``BORG_REVIEWER_VOTER_WEIGHT``.
    Subsequent calls return the existing Voter without touching its weight, so
    operators can hand-tune weights via the admin without losing them.
    """
    voter, _ = Voter.objects.get_or_create(
        kind=Voter.Kind.HUMAN,
        identifier=user.get_username(),
        defaults={"weight": conf.reviewer_voter_weight()},
    )
    return voter
```

- [ ] **Step 9: Run — expect pass**

Run: `uv run pytest tests/test_reviewers.py -v`
Expected: 3 passed.

- [ ] **Step 10: Sanity-check the broader suite still loads**

Run: `uv run pytest -q`
Expected: 99 passed (96 from Plan 1+2 + 3 new). The admin URL conf and contrib apps are loaded; existing tests must not regress.

- [ ] **Step 11: Commit**

```bash
git add tests/ django_borg/conf.py django_borg/reviewers.py
git commit -m "feat: admin test infra and reviewer voter helper"
```

---

## Task 2: Voter, Rule, Vote ModelAdmins

**Files:**
- Create: `django_borg/admin.py`
- Create: `tests/test_admin/__init__.py`
- Create: `tests/test_admin/test_simple_admins.py`

- [ ] **Step 1: Create `tests/test_admin/__init__.py`**

```python
```

(empty file)

- [ ] **Step 2: Write failing tests**

Create `tests/test_admin/test_simple_admins.py`:

```python
import pytest

from django_borg.models import Rule, TargetSchema, Vote, Voter
from tests import factories


@pytest.mark.django_db
def test_voter_changelist_renders(admin_client):
    factories.AiVoterFactory()
    response = admin_client.get("/admin/django_borg/voter/")
    assert response.status_code == 200
    assert b"ai-test" in response.content


@pytest.mark.django_db
def test_voter_can_be_added_via_admin(admin_client):
    response = admin_client.post(
        "/admin/django_borg/voter/add/",
        {
            "kind": "human",
            "identifier": "bob",
            "weight": "50",
        },
    )
    assert response.status_code in (302, 200)
    assert Voter.objects.filter(kind="human", identifier="bob", weight=50).exists()


@pytest.mark.django_db
def test_rule_changelist_renders(admin_client):
    schema = TargetSchema.objects.create(name="Product")
    factories.FieldRuleFactory(
        target_schema=schema,
        source_pattern="Farbe",
        target="color",
    )
    response = admin_client.get("/admin/django_borg/rule/")
    assert response.status_code == 200
    assert b"Farbe" in response.content


@pytest.mark.django_db
def test_rule_kind_filter_present(admin_client):
    response = admin_client.get("/admin/django_borg/rule/")
    assert response.status_code == 200
    # The list_filter renders the choice labels in the right sidebar.
    assert b"By kind" in response.content


@pytest.mark.django_db
def test_vote_changelist_renders(admin_client):
    src = TargetSchema.objects.create(name="Product")
    voter = factories.AiVoterFactory()
    mapping = factories.FieldMappingFactory(target_schema=src, source_field="Farbe")
    Vote.objects.create(mapping=mapping, voter=voter, agreed_target="color")
    response = admin_client.get("/admin/django_borg/vote/")
    assert response.status_code == 200


@pytest.mark.django_db
def test_vote_admin_disallows_change(admin_client):
    voter = factories.AiVoterFactory()
    mapping = factories.FieldMappingFactory()
    vote = Vote.objects.create(mapping=mapping, voter=voter, agreed_target="color")
    response = admin_client.get(f"/admin/django_borg/vote/{vote.pk}/change/")
    # Detail page renders but in read-only form (no save controls). We assert
    # that the form's submit row is hidden by checking has_change_permission via
    # the response context or by confirming no _save button appears.
    assert response.status_code == 200
    assert b'name="_save"' not in response.content


@pytest.mark.django_db
def test_vote_admin_disallows_delete(admin_client):
    voter = factories.AiVoterFactory()
    mapping = factories.FieldMappingFactory()
    vote = Vote.objects.create(mapping=mapping, voter=voter, agreed_target="color")
    response = admin_client.get(f"/admin/django_borg/vote/{vote.pk}/delete/")
    assert response.status_code == 403
```

- [ ] **Step 3: Run — expect 404s and a missing module**

Run: `uv run pytest tests/test_admin/test_simple_admins.py -v`
Expected: FAILs (admin URLs return 404 because no admin module is registered yet).

- [ ] **Step 4: Create `django_borg/admin.py` with the simple admins**

```python
from typing import TYPE_CHECKING

from django.contrib import admin

from django_borg.models import Rule, Vote, Voter

if TYPE_CHECKING:
    from django.http import HttpRequest


@admin.register(Voter)
class VoterAdmin(admin.ModelAdmin):
    list_display = ("identifier", "kind", "weight")
    list_filter = ("kind",)
    search_fields = ("identifier",)


@admin.register(Rule)
class RuleAdmin(admin.ModelAdmin):
    list_display = ("target_schema", "kind", "polarity", "pattern_type", "source_pattern", "target")
    list_filter = ("kind", "polarity", "pattern_type", "target_schema")
    search_fields = ("source_pattern", "target")
    autocomplete_fields = ("target_schema", "target_field")


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ("voter", "agreed_target", "content_type", "object_id", "created_at")
    list_filter = ("voter__kind", "content_type")
    search_fields = ("agreed_target", "voter__identifier")
    readonly_fields = ("voter", "agreed_target", "content_type", "object_id", "created_at")
    date_hierarchy = "created_at"

    def has_change_permission(self, request: "HttpRequest", obj: object | None = None) -> bool:
        return False

    def has_delete_permission(self, request: "HttpRequest", obj: object | None = None) -> bool:
        return False
```

- [ ] **Step 5: Run — most tests still fail because TargetSchema isn't yet registered for autocomplete**

Run: `uv run pytest tests/test_admin/test_simple_admins.py -v`
Expected: Some Voter/Rule list tests pass; the `add/` flow may fail because RuleAdmin's `autocomplete_fields = ("target_schema", "target_field")` requires those admins to register `search_fields`. We'll register them in Task 3. For now, drop the autocomplete to keep this task self-contained.

Edit `django_borg/admin.py`: remove the `autocomplete_fields = ("target_schema", "target_field")` line from `RuleAdmin`. (We'll add it back in Task 3 once those admins exist with `search_fields`.)

- [ ] **Step 6: Re-run**

Run: `uv run pytest tests/test_admin/test_simple_admins.py -v`
Expected: 7 passed.

- [ ] **Step 7: Commit**

```bash
git add django_borg/admin.py tests/test_admin/
git commit -m "feat: admin for Voter, Rule, and Vote (append-only)"
```

---

## Task 3: Schema admins with inlines

**Files:**
- Modify: `django_borg/admin.py`
- Create: `tests/test_admin/test_schema_admins.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_admin/test_schema_admins.py`:

```python
import pytest

from django_borg.models import SourceSchema, TargetField, TargetSchema


@pytest.mark.django_db
def test_target_schema_changelist_renders(admin_client):
    TargetSchema.objects.create(name="Product")
    response = admin_client.get("/admin/django_borg/targetschema/")
    assert response.status_code == 200
    assert b"Product" in response.content


@pytest.mark.django_db
def test_target_schema_detail_shows_field_inline(admin_client):
    schema = TargetSchema.objects.create(name="Product")
    TargetField.objects.create(schema=schema, name="color", is_enum=True)
    response = admin_client.get(f"/admin/django_borg/targetschema/{schema.pk}/change/")
    assert response.status_code == 200
    assert b"color" in response.content


@pytest.mark.django_db
def test_source_schema_changelist_renders(admin_client):
    SourceSchema.objects.create(name="acme-supplier")
    response = admin_client.get("/admin/django_borg/sourceschema/")
    assert response.status_code == 200
    assert b"acme-supplier" in response.content


@pytest.mark.django_db
def test_target_schema_search(admin_client):
    """RuleAdmin's autocomplete_fields requires search_fields here."""
    TargetSchema.objects.create(name="Product")
    response = admin_client.get("/admin/django_borg/targetschema/?q=Product")
    assert response.status_code == 200
    assert b"Product" in response.content
```

- [ ] **Step 2: Run — expect 404s on schema URLs**

Run: `uv run pytest tests/test_admin/test_schema_admins.py -v`
Expected: FAILs.

- [ ] **Step 3: Add schema admins**

Append to `django_borg/admin.py`:

```python
from django_borg.models import SourceField, SourceSchema, TargetField, TargetSchema


class TargetFieldInline(admin.TabularInline):
    model = TargetField
    extra = 0
    fields = ("name", "is_enum", "description")


@admin.register(TargetSchema)
class TargetSchemaAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    inlines = (TargetFieldInline,)


@admin.register(TargetField)
class TargetFieldAdmin(admin.ModelAdmin):
    list_display = ("schema", "name", "is_enum")
    list_filter = ("is_enum", "schema")
    search_fields = ("name",)
    autocomplete_fields = ("schema",)


class SourceFieldInline(admin.TabularInline):
    model = SourceField
    extra = 0
    fields = ("name",)


@admin.register(SourceSchema)
class SourceSchemaAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    inlines = (SourceFieldInline,)


@admin.register(SourceField)
class SourceFieldAdmin(admin.ModelAdmin):
    list_display = ("schema", "name")
    list_filter = ("schema",)
    search_fields = ("name",)
    autocomplete_fields = ("schema",)
```

Now restore the autocomplete on `RuleAdmin` (TargetSchema/TargetField now define `search_fields`). Find the `RuleAdmin` block and add back:

```python
    autocomplete_fields = ("target_schema", "target_field")
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_admin/ -v`
Expected: 11 passed (7 from Task 2 + 4 new).

- [ ] **Step 5: Commit**

```bash
git add django_borg/admin.py tests/test_admin/test_schema_admins.py
git commit -m "feat: schema admins with field inlines and autocomplete"
```

---

## Task 4: Mapping admins (basic)

**Files:**
- Modify: `django_borg/admin.py`
- Create: `tests/test_admin/test_mapping_admins.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_admin/test_mapping_admins.py`:

```python
import pytest

from django_borg.models import (
    FieldMapping,
    SourceSchema,
    TargetField,
    TargetSchema,
    ValueMapping,
    Vote,
)
from tests import factories


@pytest.mark.django_db
def test_field_mapping_changelist_renders(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=tgt,
    )
    response = admin_client.get("/admin/django_borg/fieldmapping/")
    assert response.status_code == 200
    assert b"Farbe" in response.content


@pytest.mark.django_db
def test_field_mapping_list_display_shows_confidence(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    voter = factories.ReviewerVoterFactory()
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=tgt,
    )
    Vote.objects.create(mapping=fm, voter=voter, agreed_target="color")
    response = admin_client.get("/admin/django_borg/fieldmapping/")
    assert response.status_code == 200
    # current_target rendered after the vote-driven recompute
    assert b"color" in response.content


@pytest.mark.django_db
def test_value_mapping_changelist_renders(admin_client):
    schema = TargetSchema.objects.create(name="Product")
    color = TargetField.objects.create(schema=schema, name="color", is_enum=True)
    ValueMapping.objects.create(target_field=color, source_value="Rot")
    response = admin_client.get("/admin/django_borg/valuemapping/")
    assert response.status_code == 200
    assert b"Rot" in response.content
```

- [ ] **Step 2: Run — expect 404s**

Run: `uv run pytest tests/test_admin/test_mapping_admins.py -v`
Expected: FAIL.

- [ ] **Step 3: Add mapping admins**

Append to `django_borg/admin.py`:

```python
from django_borg.models import FieldMapping, ValueMapping


@admin.register(FieldMapping)
class FieldMappingAdmin(admin.ModelAdmin):
    list_display = (
        "source_schema",
        "source_field",
        "target_schema",
        "current_target",
        "confidence",
        "total_weight",
        "updated_at",
    )
    list_filter = ("source_schema", "target_schema")
    search_fields = ("source_field", "current_target")
    readonly_fields = ("current_target", "confidence", "total_weight", "created_at", "updated_at")
    autocomplete_fields = ("source_schema", "target_schema")


@admin.register(ValueMapping)
class ValueMappingAdmin(admin.ModelAdmin):
    list_display = (
        "target_field",
        "source_value",
        "current_target",
        "confidence",
        "total_weight",
        "updated_at",
    )
    list_filter = ("target_field__schema",)
    search_fields = ("source_value", "current_target")
    readonly_fields = ("current_target", "confidence", "total_weight", "created_at", "updated_at")
    autocomplete_fields = ("target_field",)
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_admin/test_mapping_admins.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add django_borg/admin.py tests/test_admin/test_mapping_admins.py
git commit -m "feat: FieldMapping and ValueMapping admins"
```

---

## Task 5: NeedsReview filter

**Files:**
- Modify: `django_borg/admin.py`
- Modify: `tests/test_admin/test_mapping_admins.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_admin/test_mapping_admins.py`:

```python
@pytest.mark.django_db
def test_needs_review_filter_includes_mapping_below_thresholds(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=tgt,
    )
    ai = factories.AiVoterFactory()
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="color")  # 1 ai vote -> below weight threshold
    response = admin_client.get("/admin/django_borg/fieldmapping/?needs_review=yes")
    assert response.status_code == 200
    assert b"Farbe" in response.content


@pytest.mark.django_db
def test_needs_review_filter_excludes_zero_vote_mappings(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    FieldMapping.objects.create(
        source_schema=src,
        source_field="Untouched",
        target_schema=tgt,
    )  # zero votes -> should NOT appear
    response = admin_client.get("/admin/django_borg/fieldmapping/?needs_review=yes")
    assert response.status_code == 200
    assert b"Untouched" not in response.content


@pytest.mark.django_db
def test_needs_review_filter_excludes_graduated_mappings(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Graduated",
        target_schema=tgt,
    )
    reviewer = factories.ReviewerVoterFactory()  # weight 100 -> graduates immediately
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="title")
    response = admin_client.get("/admin/django_borg/fieldmapping/?needs_review=yes")
    assert response.status_code == 200
    assert b"Graduated" not in response.content
```

- [ ] **Step 2: Run — expect failures**

Run: `uv run pytest tests/test_admin/test_mapping_admins.py -v`
Expected: 3 new failures (the filter doesn't filter — all three mappings appear regardless).

- [ ] **Step 3: Add the `NeedsReviewFilter` class**

Append to `django_borg/admin.py` (place it above the `FieldMappingAdmin` class):

```python
from django.db.models import Q

from django_borg import conf


class NeedsReviewFilter(admin.SimpleListFilter):
    """Mapping has at least one vote but is not yet graduated.

    Mappings with zero votes are *unsurveyed*, not in need of review;
    mappings already above thresholds are *graduated* and don't need review.
    """

    title = "review status"
    parameter_name = "needs_review"

    def lookups(self, request, model_admin):
        return [("yes", "Needs review")]

    def queryset(self, request, qs):
        if self.value() != "yes":
            return qs
        min_weight = conf.min_weight()
        min_confidence = conf.min_confidence()
        return qs.exclude(total_weight=0).filter(
            Q(total_weight__lt=min_weight) | Q(confidence__lt=min_confidence),
        )
```

- [ ] **Step 4: Wire `NeedsReviewFilter` into both mapping admins**

Update `FieldMappingAdmin.list_filter` to:

```python
    list_filter = (NeedsReviewFilter, "source_schema", "target_schema")
```

Update `ValueMappingAdmin.list_filter` to:

```python
    list_filter = (NeedsReviewFilter, "target_field__schema")
```

- [ ] **Step 5: Run — expect pass**

Run: `uv run pytest tests/test_admin/test_mapping_admins.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add django_borg/admin.py tests/test_admin/test_mapping_admins.py
git commit -m "feat: NeedsReview filter on mapping admins"
```

---

## Task 6: Conflict filter

**Files:**
- Modify: `django_borg/admin.py`
- Modify: `tests/test_admin/test_mapping_admins.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_admin/test_mapping_admins.py`:

```python
@pytest.mark.django_db
def test_conflict_filter_flags_mappings_where_ai_and_human_disagree(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Disputed",
        target_schema=tgt,
    )
    ai = factories.AiVoterFactory()
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="title")
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="color")

    response = admin_client.get("/admin/django_borg/fieldmapping/?conflict=yes")
    assert response.status_code == 200
    assert b"Disputed" in response.content


@pytest.mark.django_db
def test_conflict_filter_excludes_agreement(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Agreed",
        target_schema=tgt,
    )
    ai = factories.AiVoterFactory()
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="title")
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="title")

    response = admin_client.get("/admin/django_borg/fieldmapping/?conflict=yes")
    assert response.status_code == 200
    assert b"Agreed" not in response.content


@pytest.mark.django_db
def test_conflict_filter_excludes_single_voter_kind(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="OnlyAi",
        target_schema=tgt,
    )
    ai = factories.AiVoterFactory()
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="title")

    response = admin_client.get("/admin/django_borg/fieldmapping/?conflict=yes")
    assert response.status_code == 200
    assert b"OnlyAi" not in response.content
```

- [ ] **Step 2: Run — expect failures**

Run: `uv run pytest tests/test_admin/test_mapping_admins.py -v`
Expected: 3 new failures.

- [ ] **Step 3: Add `ConflictFilter`**

Append to `django_borg/admin.py` (just below `NeedsReviewFilter`):

```python
from collections import defaultdict

from django.contrib.contenttypes.models import ContentType


class ConflictFilter(admin.SimpleListFilter):
    """Mapping has at least one AI vote and one human vote with differing target sets."""

    title = "conflict"
    parameter_name = "conflict"

    def lookups(self, request, model_admin):
        return [("yes", "AI / human disagree")]

    def queryset(self, request, qs):
        if self.value() != "yes":
            return qs
        ct = ContentType.objects.get_for_model(qs.model)
        per_mapping: dict[int, dict[str, set[str]]] = defaultdict(
            lambda: {"ai": set(), "human": set()},
        )
        votes = (
            Vote.objects.filter(content_type=ct, object_id__in=qs.values_list("pk", flat=True))
            .select_related("voter")
            .values("object_id", "voter__kind", "agreed_target")
        )
        for v in votes:
            kind = v["voter__kind"]
            if kind in ("ai", "human"):
                per_mapping[v["object_id"]][kind].add(v["agreed_target"])
        conflict_pks = [
            pk
            for pk, by_kind in per_mapping.items()
            if by_kind["ai"] and by_kind["human"] and by_kind["ai"] != by_kind["human"]
        ]
        return qs.filter(pk__in=conflict_pks)
```

- [ ] **Step 4: Wire `ConflictFilter` into both mapping admins**

Update `FieldMappingAdmin.list_filter`:

```python
    list_filter = (NeedsReviewFilter, ConflictFilter, "source_schema", "target_schema")
```

Update `ValueMappingAdmin.list_filter`:

```python
    list_filter = (NeedsReviewFilter, ConflictFilter, "target_field__schema")
```

- [ ] **Step 5: Run — expect pass**

Run: `uv run pytest tests/test_admin/test_mapping_admins.py -v`
Expected: 9 passed.

- [ ] **Step 6: Commit**

```bash
git add django_borg/admin.py tests/test_admin/test_mapping_admins.py
git commit -m "feat: Conflict filter highlights AI/human disagreements"
```

---

## Task 7: Bulk approve action

**Files:**
- Modify: `django_borg/admin.py`
- Modify: `tests/test_admin/test_mapping_admins.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_admin/test_mapping_admins.py`:

```python
@pytest.mark.django_db
def test_bulk_approve_writes_reviewer_votes(admin_client, admin_user):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=tgt,
    )
    ai = factories.AiVoterFactory()
    Vote.objects.create(mapping=fm, voter=ai, agreed_target="color")
    fm.refresh_from_db()
    assert fm.current_target == "color"

    response = admin_client.post(
        "/admin/django_borg/fieldmapping/",
        {
            "action": "approve_current_target",
            "_selected_action": [str(fm.pk)],
        },
        follow=True,
    )
    assert response.status_code == 200
    fm.refresh_from_db()
    # Reviewer vote (weight 100) added on top of the 1 ai vote -> graduated.
    assert fm.total_weight == 101
    assert fm.current_target == "color"
    # Vote was attributed to the admin user's reviewer voter
    from django_borg.reviewers import get_or_create_reviewer_voter

    reviewer = get_or_create_reviewer_voter(admin_user)
    assert Vote.objects.filter(voter=reviewer, agreed_target="color").count() == 1


@pytest.mark.django_db
def test_bulk_approve_skips_mappings_without_current_target(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    empty = FieldMapping.objects.create(
        source_schema=src,
        source_field="Empty",
        target_schema=tgt,
    )  # zero votes, current_target == ""

    response = admin_client.post(
        "/admin/django_borg/fieldmapping/",
        {
            "action": "approve_current_target",
            "_selected_action": [str(empty.pk)],
        },
        follow=True,
    )
    assert response.status_code == 200
    empty.refresh_from_db()
    assert empty.total_weight == 0  # no vote written
    # The success message reports the skip count
    messages = [m.message for m in response.context["messages"]]
    assert any("skipped" in m.lower() for m in messages)


@pytest.mark.django_db
def test_bulk_approve_works_on_value_mappings(admin_client, admin_user):
    schema = TargetSchema.objects.create(name="Product")
    color = TargetField.objects.create(schema=schema, name="color", is_enum=True)
    vm = ValueMapping.objects.create(target_field=color, source_value="Rot")
    ai = factories.AiVoterFactory()
    Vote.objects.create(mapping=vm, voter=ai, agreed_target="red")

    admin_client.post(
        "/admin/django_borg/valuemapping/",
        {
            "action": "approve_current_target",
            "_selected_action": [str(vm.pk)],
        },
        follow=True,
    )
    vm.refresh_from_db()
    assert vm.total_weight == 101
    assert vm.current_target == "red"
```

- [ ] **Step 2: Run — expect failures**

Run: `uv run pytest tests/test_admin/test_mapping_admins.py -v`
Expected: 3 new failures.

- [ ] **Step 3: Add the bulk action**

Append to `django_borg/admin.py`:

```python
from django.contrib import messages

from django_borg.reviewers import get_or_create_reviewer_voter


@admin.action(description="Approve current target as reviewer")
def approve_current_target(modeladmin, request, queryset):
    reviewer = get_or_create_reviewer_voter(request.user)
    approved = 0
    skipped = 0
    for mapping in queryset:
        if not mapping.current_target:
            skipped += 1
            continue
        Vote.objects.create(
            mapping=mapping,
            voter=reviewer,
            agreed_target=mapping.current_target,
        )
        approved += 1
    messages.success(
        request,
        f"Approved {approved} mapping(s); skipped {skipped} with no current target.",
    )
```

Wire it into both admins by adding `actions = (approve_current_target,)` to both `FieldMappingAdmin` and `ValueMappingAdmin`.

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_admin/test_mapping_admins.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add django_borg/admin.py tests/test_admin/test_mapping_admins.py
git commit -m "feat: bulk-approve action writes reviewer-weight votes"
```

---

## Task 8: Per-supplier stats on `SourceSchemaAdmin`

**Files:**
- Modify: `django_borg/admin.py`
- Modify: `tests/test_admin/test_schema_admins.py`

- [ ] **Step 1: Add the imports to the top of the file**

Edit `tests/test_admin/test_schema_admins.py`. Replace the existing import block at the top with:

```python
import pytest

from django_borg.models import FieldMapping, SourceSchema, TargetField, TargetSchema, Vote
from tests import factories
```

(`SourceSchema`, `TargetField`, `TargetSchema` were already imported; this consolidates and adds `FieldMapping`, `Vote`, and the `factories` module.)

- [ ] **Step 2: Append failing tests**

Append to `tests/test_admin/test_schema_admins.py`:

```python
@pytest.mark.django_db
def test_source_schema_detail_shows_field_mapping_count(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    FieldMapping.objects.create(source_schema=src, source_field="A", target_schema=tgt)
    FieldMapping.objects.create(source_schema=src, source_field="B", target_schema=tgt)

    response = admin_client.get(f"/admin/django_borg/sourceschema/{src.pk}/change/")
    assert response.status_code == 200
    # The count is rendered as readonly on the detail page
    assert b"Field mapping count" in response.content
    assert b">2<" in response.content or b"value=\"2\"" in response.content or b"2</" in response.content


@pytest.mark.django_db
def test_source_schema_detail_distinguishes_graduated_from_pending(admin_client):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    pending = FieldMapping.objects.create(source_schema=src, source_field="P", target_schema=tgt)
    graduated = FieldMapping.objects.create(source_schema=src, source_field="G", target_schema=tgt)
    reviewer = factories.ReviewerVoterFactory()
    ai = factories.AiVoterFactory()

    Vote.objects.create(mapping=pending, voter=ai, agreed_target="title")  # 1 ai vote -> pending
    Vote.objects.create(mapping=graduated, voter=reviewer, agreed_target="title")  # graduated

    response = admin_client.get(f"/admin/django_borg/sourceschema/{src.pk}/change/")
    assert response.status_code == 200
    body = response.content.decode()
    # Both labels render
    assert "Graduated field mapping count" in body
    assert "Pending field mapping count" in body
```

- [ ] **Step 3: Run — expect failures**

Run: `uv run pytest tests/test_admin/test_schema_admins.py -v`
Expected: 2 new failures.

- [ ] **Step 4: Add stats methods to `SourceSchemaAdmin`**

Replace the existing `SourceSchemaAdmin` class in `django_borg/admin.py` with:

```python
@admin.register(SourceSchema)
class SourceSchemaAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    inlines = (SourceFieldInline,)
    readonly_fields = (
        "field_mapping_count",
        "graduated_field_mapping_count",
        "pending_field_mapping_count",
    )

    @admin.display(description="Field mapping count")
    def field_mapping_count(self, obj: SourceSchema) -> int:
        return FieldMapping.objects.filter(source_schema=obj).count()

    @admin.display(description="Graduated field mapping count")
    def graduated_field_mapping_count(self, obj: SourceSchema) -> int:
        return FieldMapping.objects.filter(
            source_schema=obj,
            total_weight__gte=conf.min_weight(),
            confidence__gte=conf.min_confidence(),
        ).count()

    @admin.display(description="Pending field mapping count")
    def pending_field_mapping_count(self, obj: SourceSchema) -> int:
        return (
            FieldMapping.objects.filter(source_schema=obj)
            .exclude(total_weight=0)
            .exclude(
                total_weight__gte=conf.min_weight(),
                confidence__gte=conf.min_confidence(),
            )
            .count()
        )
```

- [ ] **Step 5: Run — expect pass**

Run: `uv run pytest tests/test_admin/test_schema_admins.py -v`
Expected: 6 passed (4 from Task 3 + 2 new).

- [ ] **Step 6: Commit**

```bash
git add django_borg/admin.py tests/test_admin/test_schema_admins.py
git commit -m "feat: per-supplier mapping stats on SourceSchema admin"
```

---

## Task 9: Lint, type, full-suite gate, and README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Run ruff**

Run: `uv run ruff check django_borg tests`
Expected: clean. If lint errors, fix in place; commit fixes with `style: ruff fixes`.

- [ ] **Step 2: Run ruff format check**

Run: `uv run ruff format --check django_borg tests`
Expected: clean. If formatting drift, run `uv run ruff format django_borg tests` and commit `style: apply ruff format`.

- [ ] **Step 3: Run mypy**

Run: `uv run mypy django_borg`
Expected: clean. Fix any reported issues; commit fixes with `chore: appease mypy`.

- [ ] **Step 4: Run full suite**

Run: `uv run pytest -q`
Expected: 124 passed (96 prior + 3 reviewers + 7 simple admins + 6 schema admins + 12 mapping admins). Coverage ≥ 90% on `django_borg/*`.

- [ ] **Step 5: Append admin section to `README.md`**

Insert in `README.md` directly before the line `## Documentation`:

```markdown
## Reviewer admin

Register the project's admin URLs (`path("admin/", admin.site.urls)`) and visit
`/admin/django_borg/`. Reviewers get:

- **NeedsReview filter** on FieldMapping / ValueMapping changelists — every
  mapping with at least one vote that hasn't yet graduated.
- **Conflict filter** — mappings where AI and human votes disagree.
- **Approve current target** bulk action — writes a reviewer-weight Vote for
  each selected mapping's `current_target`. With the default
  `BORG_REVIEWER_VOTER_WEIGHT = 100`, one approval graduates a mapping
  immediately.
- **Per-supplier stats** on the SourceSchema detail page — total / graduated /
  pending field mapping counts.

The reviewer's identity is auto-mapped from `request.user` to a borg
`Voter(kind=human, identifier=username)` row. Hand-tune individual reviewer
weights via the Voter admin.
```

- [ ] **Step 6: Sanity-check imports**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "docs: document reviewer admin in README"
```

---

## Self-review checklist (run after Task 9)

- [ ] Triage queue — `NeedsReviewFilter` on both mapping admins (Task 5).
- [ ] Conflict view — `ConflictFilter` on both mapping admins (Task 6).
- [ ] Rule editor — `RuleAdmin` (Task 2).
- [ ] Per-supplier view — `SourceSchemaAdmin` stats (Task 8).
- [ ] Bulk actions first-class — `approve_current_target` on both mapping admins (Task 7).
- [ ] Reviewer actions write high-weight votes — covered by Task 7 test.
- [ ] No placeholders. No undefined references.
- [ ] Type/name consistency: `get_or_create_reviewer_voter`, `NeedsReviewFilter`, `ConflictFilter`, `approve_current_target` used identically in tests and impl.

---

## Out of scope (still — separate plans)

- **Live preview of rule matches** — defer until rule volume justifies it.
- **Drift detection** — Plan 4.
- **Bulk reject / lock actions** — admins can hand-craft Votes per-mapping; bulk variants need a sentinel-target design that aligns with future reviewer workflows.
- **Custom admin theming or HTMX live updates** — out of scope.
