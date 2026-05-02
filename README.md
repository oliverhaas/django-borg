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

## Documentation

Full documentation at [oliverhaas.github.io/django-borg](https://oliverhaas.github.io/django-borg/)

## License

MIT
