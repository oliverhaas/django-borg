# django-borg

[![PyPI version](https://img.shields.io/pypi/v/django-borg.svg?style=flat)](https://pypi.org/project/django-borg/)
[![Python versions](https://img.shields.io/pypi/pyversions/django-borg.svg)](https://pypi.org/project/django-borg/)
[![CI](https://github.com/oliverhaas/django-borg/actions/workflows/ci.yml/badge.svg)](https://github.com/oliverhaas/django-borg/actions/workflows/ci.yml)

> *"You must comply."*

AI-bootstrapped, vote-curated schema mapping for Django. Assimilate heterogeneous supplier data into your canonical schema -- AI proposes mappings, humans curate them, votes accumulate, and once a mapping is trusted it runs deterministically. No AI call, no surprises.

## Status

Pre-alpha. Under active development.

## Installation

```console
pip install django-borg
```

## Quickstart

```python
from django_borg import SchemaAssimilator, FakeInferencer
from myapp.models import Product

# In a real project, swap FakeInferencer for an Inferencer that calls your LLM.
ai = FakeInferencer(
    field_map={"Farbe": "color", "Titel": "title"},
    value_map={("color", "Rot"): "red"},
)

borg = SchemaAssimilator(target_schema=Product, ai=ai)

for raw in supplier_feed:  # e.g. {"Titel": "T-Shirt", "Farbe": "Rot"}
    result = borg.assimilate(raw, source="acme-supplier")
    if result.unresolved:
        log.warning("Could not resolve: %s", result.unresolved)
    result.product.save()
```

Each AI inference is recorded as a vote on the corresponding mapping. Once a mapping crosses `BORG_MIN_WEIGHT` (default 5) and `BORG_MIN_CONFIDENCE` (default 0.9), subsequent calls skip the AI entirely. Reviewer-authored votes graduate mappings instantly thanks to their higher weight.

### Extraction (free-text columns)

When a supplier ships unstructured text (e.g. a `description` column), declare it
as an extraction source and let the AI pull multiple canonical fields out of it:

```python
borg = SchemaAssimilator(
    target_schema=Product,
    ai=ai,                              # ai must implement Inferencer.extract(...)
    extract_from=["description"],
)

result = borg.assimilate(
    {
        "Titel": "T-Shirt",
        "description": "100% Baumwolle, rotes T-Shirt, Größe M",
    },
    source="acme-supplier",
)
# result.product.color == "red"  (extracted "rotes", canonicalised via ValueMapping)
# result.cost.extraction_calls == 1
```

Direct field mappings always run first; extraction only fills target fields that
weren't populated in the direct pass. You can also flag extraction sources via a
DO rule whose target is `EXTRACT_SENTINEL` (`"__extract__"`) — useful when the
choice of extraction source is itself something you want to vote on.

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

## Drift detection

Re-run AI inference on already-graduated mappings to catch supplier or model
drift:

```python
from datetime import timedelta
from django_borg import DriftRunner

runner = DriftRunner(target_schema=Product, ai=ai)
result = runner.run(
    source="acme-supplier",         # restrict field mappings to one supplier (optional)
    older_than=timedelta(days=30),  # skip mappings whose latest AI vote is fresh (optional)
    limit=100,                       # cap total iterations (optional)
)
# result.field_mappings_revoted, result.value_mappings_revoted,
# result.skipped_recent, result.skipped_ai_failure
```

Each AI re-vote is a normal Vote — the post_save signal recomputes confidence,
and any divergence shows up in the **Drift** admin filter on FieldMapping /
ValueMapping changelists ("latest AI vote disagrees with current target"). When
human-weight votes still keep a mapping graduated despite AI drift, the drift
filter still flags it for review.

Schedule the runner from a Celery beat task, a cron job, or your own
management command — the package leaves cadence to the consumer.

## Reference AI adapter

For consumers using a structured-output LLM client, the package ships
`StructuredOutputInferencer` — a duck-typed wrapper that turns any agent with
a `run_sync(prompt, *, output_type=PydanticModel)` shape into an
`Inferencer`. Pydantic AI's `Agent` matches verbatim:

```python
# pip install django-borg[adapters] pydantic-ai
from pydantic_ai import Agent
from django_borg import SchemaAssimilator, StructuredOutputInferencer

ai = StructuredOutputInferencer(agent=Agent("openai:gpt-4o"))
borg = SchemaAssimilator(target_schema=Product, ai=ai)
```

For Instructor or a raw OpenAI client with JSON mode, write a five-line
adapter that exposes the same `run_sync` shape. Defaults: target field
discovery queries Django's `TargetField` table; prompts are short English
strings overridable per-method (`prompt_for_field`, `prompt_for_value`,
`prompt_for_extract`).

The `[adapters]` extra installs `pydantic` only — no LLM client is bundled.

## Documentation

Full documentation at [oliverhaas.github.io/django-borg](https://oliverhaas.github.io/django-borg/)

## License

MIT
