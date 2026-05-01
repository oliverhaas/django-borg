---
status: in-progress
repo: https://github.com/oliverhaas/django-borg
effort: large
impact: high
---

# django-borg

> *"You must comply."*

Assimilate heterogeneous supplier data into your canonical schema. AI proposes mappings, humans curate them, votes accumulate, and once a mapping is trusted it runs deterministically -- no AI call, no surprises. Resistance is futile.

## Problem

Ecommerce platforms ingest product data from many suppliers, each with their own schemas, their own values, their own free-text descriptions, and increasingly their own image-extracted attributes. The work of conforming all of this into one canonical product schema is endless and largely invisible.

Modern AI handles each individual mapping near-perfectly: given supplier field `Farbe = "Rot"` and a target schema with field `color`, an LLM will reliably produce `color = "red"`. The problem is that this knowledge is *not retained*. Every batch re-incurs the AI call, every batch is non-deterministic, and human reviewers correcting a wrong mapping have nowhere to record their correction in a way that prevents the same mistake next week.

The missing piece: a system where the AI bootstraps mappings, every inference is logged as a vote, human reviewers contribute high-weight votes (or hard rules), and a mapping graduates to deterministic execution once trust is high enough. Wrong mappings are corrected once; right mappings stop costing AI tokens.

Existing tools cover adjacent shapes but not this one:

- **LLM extraction libraries** (Instructor, Pydantic AI, LangExtract, Outlines) -- one-shot structured extraction. No persistence, no learning, no human-in-loop curation.
- **PIM platforms** (Akeneo, Pimcore) -- rich product modelling and import rules, but rules are entirely human-authored. No AI bootstrapping, no confidence accumulation.
- **Schema-matching ML tools** (Tamr, OpenRefine + reconciliation) -- closest in spirit. Tamr is the proprietary commercial answer; nothing comparable exists open source for Django.
- **Hand-rolled supplier importers** -- the status quo. Each project rebuilds the same loop badly.

## Scope

### Architecture: three layers, evaluated in order

| Layer | Borg lore | Behaviour |
|---|---|---|
| 1. **Rules** | Drone directives | Human-authored DO/DON'T (exact match or regex). Hard win. |
| 2. **Learned mappings** | Assimilated knowledge | Stored mappings with weighted confidence. Used deterministically when confidence ≥ threshold. |
| 3. **AI fallback** | The Queen | Invoked when no rule and confidence < threshold. Result is recorded as a new vote in layer 2. |

### Three mapping types

1. **Field → field**: source column `Farbe` → target field `color`. Finite (~dozens per supplier). Exact-match keyed.
2. **Value → value (within a known field)**: in `color`, `Rot` → `red`. Per-field vocabulary, potentially large.
3. **Value → field extraction**: from unstructured text or image-extracted captions like `"100% Baumwolle, rotes T-Shirt, Größe M"`, extract `material=cotton`, `color=red`, `size=M`. Output of an extractor feeds back into type 2 for canonicalisation.

### Vote-weighted confidence

Every inference -- AI or human -- is recorded as a vote on a `(source, target)` pair. Voters have a weight (`ai=1`, `reviewer=100`, `admin=∞/lock`). Confidence on a mapping is the weighted agreement rate. A mapping graduates to deterministic when:

- weight-sum of votes ≥ threshold (e.g. 5 AI votes or 1 reviewer vote), **and**
- weighted agreement ≥ threshold (e.g. 0.9), **and**
- no DON'T rule applies.

Periodic AI "review runs" can revote on existing high-confidence mappings to detect drift. A drift event surfaces in the reviewer queue.

### Core models (sketch)

```
TargetSchema       # your canonical schema (registered Django model or config)
SourceSchema       # per-supplier introspected schema (auto-discovered from imports)

Mapping (abstract)
    ├── FieldMapping     # (source_schema, source_field) → target_field
    ├── ValueMapping     # (target_field, source_value) → target_value
    └── Extraction       # unstructured_text → list of (target_field, value)

Vote                 # (mapping, voter, weight, agreed_target, ts)
Rule                 # (scope, pattern, target, polarity=DO|DONT) -- evaluated first
Voter                # (kind=ai|human, weight, identifier)
```

Append-only `Vote` table. `Mapping.confidence` is a denormalised cached column rebuilt by triggers or signals on vote insert.

### Mapping decision (pseudocode)

```python
def resolve(source_field, source_value=None) -> Resolution:
    if rule := rules.match(source_field, source_value):
        return rule.target  # DO wins, DONT blocks
    if mapping := mappings.lookup(source_field, source_value, min_confidence=0.9):
        return mapping.target
    target = ai.infer(source_field, source_value)  # or extract
    Vote.objects.create(mapping=..., voter=ai_voter, agreed_target=target)
    return target
```

### AI integration

Pluggable backend. The consumer provides a callable conforming to a small protocol:

```python
class Inferencer(Protocol):
    def map_field(self, source: str, target_schema: TargetSchema) -> str: ...
    def map_value(self, source: str, field: TargetField) -> str: ...
    def extract(self, text: str, target_schema: TargetSchema) -> dict: ...
```

A reference adapter ships for Pydantic AI / Instructor; the package itself does not lock a vendor or hold an API key. Image-OCR / vision extraction is the consumer's responsibility -- they hand the package extracted text.

### Reviewer UI (Django admin)

Built on Django admin with custom changelist views:

- **Triage queue**: low-confidence and drift-flagged mappings, sorted by impact (frequency × confidence gap).
- **Conflict view**: mappings where AI and human votes disagree.
- **Rule editor**: author DO/DONT rules with live preview against a sample of existing data.
- **Per-supplier view**: full picture of one supplier's mappings -- coverage, AI cost, deterministic ratio.

Each reviewer action (approve, reject, edit, lock) writes a high-weight vote. Bulk actions are first-class.

### Ingestion API

```python
borg = SchemaAssimilator(target_schema=Product, ai=my_inferencer)

for raw_item in supplier_feed:
    result = borg.assimilate(raw_item, source=supplier)
    # result.product: Product instance with mapped fields
    # result.unresolved: list of fields that fell through to AI (queued for review)
    # result.cost: { ai_calls: 2, deterministic_hits: 47 }
```

### Out of scope (v0.1)

- Image OCR / vision extraction -- consumer provides extracted text.
- Full PIM features (variants, pricing, category trees, channel syndication) -- this is a mapping layer, not a PIM.
- Multi-tenancy beyond standard Django patterns.
- Streaming / Kafka-style ingestion -- batch and request-scoped only.
- Automatic schema discovery beyond reading column headers / JSON keys.

## Prior art

- [Tamr](https://www.tamr.com/) -- commercial, proprietary, the closest spiritual predecessor. Human-guided ML for data unification. Pricey and not Django-native.
- [Akeneo PIM](https://www.akeneo.com/) / [Pimcore](https://pimcore.com/) -- production PIM platforms with import rules, but no AI bootstrapping or confidence-driven graduation.
- [OpenRefine](https://openrefine.org/) + reconciliation services -- interactive, manual, not embeddable. Conceptually adjacent.
- [Instructor](https://github.com/jxnl/instructor) / [Pydantic AI](https://ai.pydantic.dev/) / [LangExtract](https://github.com/google/langextract) / [Outlines](https://github.com/dottxt-ai/outlines) -- structured-output libraries. One-shot, no learning, no curation. Candidate AI backends, not competitors.
- [dedupe.io](https://github.com/dedupeio/dedupe) / [splink](https://github.com/moj-analytical-services/splink) -- entity resolution / record linkage. Adjacent problem (matching records), not field/value mapping.
- Hand-rolled supplier importers -- the status quo.

## Design notes

- **Why a Django app rather than a library**: the reviewer-UI and audit trail are most of the value. Django admin gives that nearly for free. The pure-Python mapping engine could be factored out as `borg-core` later if needed.
- **Three mapping types vs. one unified store**: tempting to model everything as a generic `(source, target, context)` triple, but field, value, and extraction have different lookup patterns and different AI prompts. Three explicit subclasses keep the queries fast and the prompts targeted.
- **Voter weights as a config**, not hardcoded: lets projects tune trust to their workflow (a senior reviewer in a regulated domain might be `weight=∞`; a crowd-sourced reviewer pool might be `weight=10`).
- **Drift detection** is what justifies the vote log over a simple confidence float. Suppliers change their schemas, AI models change their behaviour. Re-running inference periodically and seeing votes diverge is the signal.
- **Naming**: `django-borg` is playful and on-theme (assimilation of disparate sources into a canonical collective). Trademark risk is minimal -- `borgbackup` has used the name in open source for years. If a more sober name is wanted later: `django-conform`, `django-canonize`, or `django-distillery`.
