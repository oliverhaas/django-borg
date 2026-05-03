# django-borg simple example

A self-contained Django project demonstrating django-borg end to end:

- a target `Product` model with enum fields (`color`, `size`)
- a `FakeInferencer` pre-loaded with German → English mappings (no API key needed)
- two management commands: `borg_ingest` and `borg_drift`
- Django admin wired up so you can review mappings in your browser

## Run it

From this directory (with `uv` resolving the editable django-borg install in the
parent repo):

```bash
# 1. Apply migrations
uv run python manage.py migrate

# 2. Create an admin user (optional, only needed for the admin UI)
uv run python manage.py createsuperuser

# 3. Ingest the bundled supplier feed
uv run python manage.py borg_ingest

# 4. Ingest a feed with free-text descriptions (extraction path)
uv run python manage.py borg_ingest --extract

# 5. Re-run AI inference on graduated mappings to detect drift
uv run python manage.py borg_drift

# 6. Browse the admin
uv run python manage.py runserver
# -> http://127.0.0.1:8000/admin/django_borg/
```

## What you'll see

After step 3, look at `/admin/django_borg/fieldmapping/`:

- Each supplier column (`Titel`, `Farbe`, `Größe`) shows up as a `FieldMapping`
  with `confidence=1.0` and a growing `total_weight` (one AI vote per row
  ingested).
- After 5 rows, mappings cross `BORG_MIN_WEIGHT=5` and graduate to
  deterministic — subsequent ingests skip the AI for those columns.

In `/admin/django_borg/valuemapping/` you'll see one row per `(target_field,
source_value)` pair. Click any of them and use the **Approve current target**
bulk action to write a reviewer-weight Vote (default 100), graduating the
mapping immediately.

The `--extract` path demonstrates pulling structured fields out of unstructured
text. Try the **Drift** filter on the FieldMapping changelist after running
`borg_drift` — it flags any mapping whose latest AI vote disagrees with its
`current_target`.

## Wiring a real LLM

Swap `catalog/inferencer.py` for the real reference adapter:

```python
# pip install "django-borg[adapters]" pydantic-ai openai
from pydantic_ai import Agent
from django_borg import StructuredOutputInferencer

DEMO_AI = StructuredOutputInferencer(agent=Agent("openai:gpt-4o"))
```

The rest of the example — models, management commands, admin — stays the same.

## File map

```
manage.py                                # standard Django entrypoint
simpleshop/
  settings.py                            # admin + django_borg + catalog wired up
  urls.py                                # /admin/ only
catalog/
  models.py                              # Product (target schema)
  inferencer.py                          # FakeInferencer with realistic translations
  sample_data.py                         # ACME_FEED + ACME_DESCRIPTIONS
  management/commands/
    borg_ingest.py                       # SchemaAssimilator demo
    borg_drift.py                        # DriftRunner demo
```
