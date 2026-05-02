# django-borg Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the third mapping type — **extraction** — so that unstructured text columns (e.g. a free-text product description) can produce multiple canonical fields in one shot, with the extracted values then flowing through the existing value-mapping layer.

**Architecture:** Extend the `Inferencer` protocol with an `extract()` method; add a two-pass orchestration to `SchemaAssimilator.assimilate` (direct mappings first, extractions second so direct mappings always win on conflicts); trigger extraction via either an explicit `extract_from=` init argument or a DO-rule whose target is the sentinel `__extract__`. **No new database models** in this plan — the spec's `Extraction` mapping subclass (with its own vote log) is deferred until the v0.1 wiring proves out and the right key-shape becomes obvious.

**Tech Stack:** Django 5.2+, Python 3.12+, pytest-django, factory-boy, the existing django-borg core engine (Plan 1).

---

## What this plan does NOT deliver

- No `Extraction` Mapping subclass / no extraction-specific Vote log. Each AI extraction is a fresh call; the values it produces still flow through `ValueMapping`, which **is** vote-curated. Caching the extraction itself is deferred — blobs of text are usually unique, so the cache hit rate is near zero, and the right schema needs more data.
- No image/OCR support — consumers still hand the package extracted text.
- No reviewer UI, no drift detection, no real Pydantic AI / Instructor adapter (separate plans).

## File layout impacted

```
django_borg/
  ai.py                  # +Inferencer.extract, +FakeInferencer.extract
  ingestion.py           # +AssimilationCost.extraction_calls,
                         # +SchemaAssimilator(extract_from=...),
                         # +two-pass assimilate
  resolution.py          # +EXTRACT_SENTINEL constant

tests/
  test_ai.py             # +extract tests on FakeInferencer
  test_ingestion.py      # +extraction tests on SchemaAssimilator
README.md                # +extraction section
```

## Key design decisions (locked in this plan)

- **Extraction is a fallback for free-text columns**, not a parallel mapping graph. A source column either resolves to one target field (existing path) or, if marked for extraction, produces a dict of target-field → raw-value pairs. Each pair is then canonicalised via the existing `resolve_value` for enum fields, or copied raw for free-text fields.
- **Two passes inside `assimilate`.** Pass 1 handles direct field mappings and collects extraction inputs. Pass 2 calls `ai.extract()` once per extraction source and fills only target fields not already populated. This gives direct mappings precedence (they're typically higher-confidence) and lets us pass `target_fields` to the inferencer pre-filtered to the still-unfilled set, shrinking the prompt.
- **Sentinel string `__extract__`** lives in `django_borg.resolution` so it's importable wherever it's needed. A `Rule` whose `target` equals this sentinel routes its source field into extraction.
- **`extract_from` init argument is a convenience layer over rules** — it's an in-memory `set[str]` of source field names, no DB write at init, no first-class status. Rules persist; init-arg is for ad-hoc declaration.
- **Inferencer.extract signature** takes the unstructured text plus the list of `target_fields` we want the AI to look for. The AI returns `dict[target_field_name, raw_value]` — keys must be a subset of `target_fields`. Unknown keys are silently dropped.
- **Cost accounting**: an `extract()` call increments both `ai_calls` (it is an AI call) and a new `extraction_calls` counter (so consumers can see how often the extraction path fired without arithmetic).
- **First-wins at the target-field level**: if pass 1 already filled `mapped["color"]`, an extracted `color` from pass 2 is dropped. This is enforced *after* the AI call (we still query the API for the unfilled set, but a later extraction in the same batch won't clobber an earlier one either).
- **Extraction failure is recoverable**: if `ai.extract` raises, the source field is added to `unresolved`, but pass-1 results stand. The batch as a whole still produces a usable product instance.
- **Empty extraction text is skipped silently** — no AI call, no cost. Same rule as `_resolve_value_or_raw` already applies for blank values.

---

## Task 1: Add `extract` to the Inferencer protocol and `FakeInferencer`

**Files:**
- Modify: `django_borg/ai.py`
- Modify: `tests/test_ai.py`

- [ ] **Step 1: Append failing tests for `extract`**

Append to `tests/test_ai.py`:

```python
def test_fake_inferencer_extract_returns_configured_dict():
    fake = FakeInferencer(
        extract_map={"100% Baumwolle, rotes T-Shirt, Größe M": {"material": "cotton", "color": "rotes", "size": "M"}},
    )
    out = fake.extract(
        "100% Baumwolle, rotes T-Shirt, Größe M",
        target_schema="Product",
        target_fields=["material", "color", "size"],
    )
    assert out == {"material": "cotton", "color": "rotes", "size": "M"}


def test_fake_inferencer_extract_filters_to_requested_fields():
    fake = FakeInferencer(
        extract_map={"blob": {"material": "cotton", "color": "red", "noise": "ignored"}},
    )
    out = fake.extract("blob", target_schema="Product", target_fields=["material", "color"])
    assert out == {"material": "cotton", "color": "red"}


def test_fake_inferencer_extract_raises_on_unknown_text():
    fake = FakeInferencer()
    with pytest.raises(LookupError):
        fake.extract("unseen", target_schema="Product", target_fields=["color"])


def test_fake_inferencer_records_extract_calls():
    fake = FakeInferencer(extract_map={"blob": {"color": "red"}})
    fake.extract("blob", target_schema="Product", target_fields=["color"])
    assert fake.calls == [("extract", "blob", "Product", ("color",))]
```

- [ ] **Step 2: Run — expect failures**

Run: `uv run pytest tests/test_ai.py -v`
Expected: FAIL — `FakeInferencer.__init__() got an unexpected keyword argument 'extract_map'` and `AttributeError: ... 'extract'`.

- [ ] **Step 3: Extend `Inferencer` and `FakeInferencer`**

Replace the body of `django_borg/ai.py`:

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class Inferencer(Protocol):
    """Pluggable AI backend.

    Implementations may call any LLM. The package itself does not bundle a vendor.
    """

    def map_field(self, source: str, *, target_schema: str) -> str: ...

    def map_value(self, source: str, *, target_field: str) -> str: ...

    def extract(
        self,
        text: str,
        *,
        target_schema: str,
        target_fields: list[str],
    ) -> dict[str, str]: ...


class FakeInferencer:
    """Deterministic in-memory inferencer for tests and offline reference use."""

    def __init__(
        self,
        field_map: dict[str, str] | None = None,
        value_map: dict[tuple[str, str], str] | None = None,
        extract_map: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._field_map = dict(field_map or {})
        self._value_map = dict(value_map or {})
        self._extract_map = dict(extract_map or {})
        self.calls: list[tuple] = []

    def map_field(self, source: str, *, target_schema: str) -> str:
        self.calls.append(("map_field", source, target_schema))
        try:
            return self._field_map[source]
        except KeyError as exc:
            raise LookupError(f"FakeInferencer has no field mapping for {source!r}") from exc

    def map_value(self, source: str, *, target_field: str) -> str:
        self.calls.append(("map_value", source, target_field))
        try:
            return self._value_map[(target_field, source)]
        except KeyError as exc:
            raise LookupError(
                f"FakeInferencer has no value mapping for {target_field!r}, {source!r}",
            ) from exc

    def extract(
        self,
        text: str,
        *,
        target_schema: str,
        target_fields: list[str],
    ) -> dict[str, str]:
        self.calls.append(("extract", text, target_schema, tuple(target_fields)))
        try:
            full = self._extract_map[text]
        except KeyError as exc:
            raise LookupError(f"FakeInferencer has no extraction for {text!r}") from exc
        return {k: v for k, v in full.items() if k in set(target_fields)}
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_ai.py -v`
Expected: 9 passed (5 existing + 4 new).

- [ ] **Step 5: Commit**

```bash
git add django_borg/ai.py tests/test_ai.py
git commit -m "feat: add extract() to Inferencer protocol and FakeInferencer"
```

---

## Task 2: Add `extraction_calls` to `AssimilationCost`

**Files:**
- Modify: `django_borg/ingestion.py`
- Modify: `tests/test_ingestion.py`

- [ ] **Step 1: Append failing test**

Append to `tests/test_ingestion.py`:

```python
def test_assimilation_cost_records_extraction():
    cost = AssimilationCost()
    cost.record_extraction()
    cost.record_extraction()
    assert cost.extraction_calls == 2
    assert cost.ai_calls == 0  # extraction call counter is independent
```

- [ ] **Step 2: Run — expect failure**

Run: `uv run pytest tests/test_ingestion.py::test_assimilation_cost_records_extraction -v`
Expected: FAIL — `AttributeError: 'AssimilationCost' object has no attribute 'record_extraction'`.

- [ ] **Step 3: Add `extraction_calls` and `record_extraction`**

Edit `django_borg/ingestion.py`. Replace the `AssimilationCost` dataclass:

```python
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
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_ingestion.py::test_assimilation_cost_records_extraction -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add django_borg/ingestion.py tests/test_ingestion.py
git commit -m "feat: track extraction call count separately on AssimilationCost"
```

---

## Task 3: Define `EXTRACT_SENTINEL` and accept `extract_from` on `SchemaAssimilator`

**Files:**
- Modify: `django_borg/resolution.py`
- Modify: `django_borg/ingestion.py`
- Modify: `tests/test_ingestion.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_ingestion.py`:

```python
from django_borg.resolution import EXTRACT_SENTINEL


def test_extract_sentinel_value():
    assert EXTRACT_SENTINEL == "__extract__"


@pytest.mark.django_db
def test_assimilator_accepts_extract_from_iterable():
    borg = SchemaAssimilator(
        target_schema=Product,
        ai=FakeInferencer(),
        extract_from=["description", "Beschreibung"],
    )
    assert borg.extract_from == {"description", "Beschreibung"}


@pytest.mark.django_db
def test_assimilator_extract_from_defaults_to_empty():
    borg = SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    assert borg.extract_from == set()
```

- [ ] **Step 2: Run — expect ImportError**

Run: `uv run pytest tests/test_ingestion.py -v`
Expected: FAIL — `cannot import name 'EXTRACT_SENTINEL'` and `unexpected keyword argument 'extract_from'`.

- [ ] **Step 3: Add the sentinel to `resolution.py`**

Edit `django_borg/resolution.py`. Just below the `ResolutionSource` enum (after line containing `AI = "ai"`), insert:

```python
EXTRACT_SENTINEL = "__extract__"
"""Reserved target value that routes a source field into the extraction path."""
```

- [ ] **Step 4: Add `extract_from` to `SchemaAssimilator.__init__`**

Edit `django_borg/ingestion.py`. Replace the `__init__` of `SchemaAssimilator`:

```python
    def __init__(
        self,
        *,
        target_schema: type[django_models.Model],
        ai: Inferencer,
        extract_from: Iterable[str] | None = None,
    ) -> None:
        self.target_model = target_schema
        self.ai = ai
        self.extract_from: set[str] = set(extract_from or ())
        self.target_schema = self._sync_target_schema(target_schema)
        self.ai_voter = self._ensure_ai_voter()
```

Add `from collections.abc import Iterable` to the top of the file (after the `from __future__` line).

- [ ] **Step 5: Run — expect pass**

Run: `uv run pytest tests/test_ingestion.py -v`
Expected: 18 passed (14 from Plan 1 + 1 from Task 2 + 3 new).

- [ ] **Step 6: Commit**

```bash
git add django_borg/resolution.py django_borg/ingestion.py tests/test_ingestion.py
git commit -m "feat: add EXTRACT_SENTINEL and extract_from option to assimilator"
```

---

## Task 4: Two-pass `assimilate` with extraction handling

**Files:**
- Modify: `django_borg/ingestion.py`
- Modify: `tests/test_ingestion.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_ingestion.py`:

```python
@pytest.fixture
def borg_with_extract(db):
    ai = FakeInferencer(
        field_map={"Titel": "title"},
        value_map={
            ("color", "rotes"): "red",
            ("size", "M"): "M",
        },
        extract_map={
            "100% Baumwolle, rotes T-Shirt, Größe M": {
                "color": "rotes",
                "size": "M",
            },
        },
    )
    return SchemaAssimilator(
        target_schema=Product,
        ai=ai,
        extract_from=["description"],
    )


@pytest.mark.django_db
def test_assimilate_runs_extraction_for_extract_from_source(borg_with_extract):
    result = borg_with_extract.assimilate(
        {
            "Titel": "T-Shirt",
            "description": "100% Baumwolle, rotes T-Shirt, Größe M",
        },
        source="acme",
    )
    assert result.product.title == "T-Shirt"
    assert result.product.color == "red"
    assert result.product.size == "M"


@pytest.mark.django_db
def test_assimilate_extraction_increments_extraction_calls(borg_with_extract):
    result = borg_with_extract.assimilate(
        {"description": "100% Baumwolle, rotes T-Shirt, Größe M"},
        source="acme",
    )
    assert result.cost.extraction_calls == 1


@pytest.mark.django_db
def test_assimilate_skips_extraction_for_blank_text(borg_with_extract):
    result = borg_with_extract.assimilate(
        {"description": ""},
        source="acme",
    )
    assert result.cost.extraction_calls == 0
    # No AI calls at all -- blank text short-circuits.
    assert result.cost.ai_calls == 0


@pytest.mark.django_db
def test_assimilate_direct_mapping_wins_over_extraction(borg_with_extract):
    # Direct mapping for "color" via ValueMapping graduation
    schema = TargetSchema.objects.get(name="Product")
    color = TargetField.objects.get(schema=schema, name="color")
    src = SourceSchema.objects.get_or_create(name="acme")[0]
    direct_color_field = FieldMapping.objects.create(
        source_schema=src,
        source_field="Color",
        target_schema=schema,
    )
    color_value = ValueMapping.objects.create(target_field=color, source_value="blau")
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=direct_color_field, voter=reviewer, agreed_target="color")
    Vote.objects.create(mapping=color_value, voter=reviewer, agreed_target="blue")

    result = borg_with_extract.assimilate(
        {
            "Color": "blau",
            "description": "100% Baumwolle, rotes T-Shirt, Größe M",
        },
        source="acme",
    )
    # Direct mapping picks blue; extraction's "rotes -> red" does NOT clobber it.
    assert result.product.color == "blue"
    # Extraction still runs (size needs filling) -- it just respects already-mapped fields.
    assert result.product.size == "M"


@pytest.mark.django_db
def test_assimilate_extraction_failure_marks_unresolved(db):
    ai = FakeInferencer()  # empty extract_map -> raises
    borg = SchemaAssimilator(
        target_schema=Product,
        ai=ai,
        extract_from=["description"],
    )
    result = borg.assimilate({"description": "anything"}, source="acme")
    assert "description" in result.unresolved
    # Pass 1 didn't raise; we just lose the extraction output.
    assert result.product.title == ""


@pytest.mark.django_db
def test_assimilate_extraction_passes_only_unfilled_target_fields(borg_with_extract):
    # Pre-fill 'size' through a graduated value mapping so extraction is asked only for color.
    schema = TargetSchema.objects.get(name="Product")
    size = TargetField.objects.get(schema=schema, name="size")
    src_schema = SourceSchema.objects.get_or_create(name="acme")[0]
    size_field = FieldMapping.objects.create(
        source_schema=src_schema,
        source_field="Größe",
        target_schema=schema,
    )
    size_value = ValueMapping.objects.create(target_field=size, source_value="M")
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=size_field, voter=reviewer, agreed_target="size")
    Vote.objects.create(mapping=size_value, voter=reviewer, agreed_target="M")

    borg_with_extract.assimilate(
        {"Größe": "M", "description": "100% Baumwolle, rotes T-Shirt, Größe M"},
        source="acme",
    )
    extract_calls = [c for c in borg_with_extract.ai.calls if c[0] == "extract"]
    assert len(extract_calls) == 1
    _, _, _, requested_fields = extract_calls[0]
    assert "size" not in requested_fields
    assert "color" in requested_fields
```

- [ ] **Step 2: Run — expect failures**

Run: `uv run pytest tests/test_ingestion.py -v`
Expected: 6 new failures (existing path doesn't run extraction at all).

- [ ] **Step 3: Rewrite `assimilate` with two passes**

Edit `django_borg/ingestion.py`. Replace `assimilate` (and add a private helper for the extraction pass):

```python
    def assimilate(self, raw_item: dict[str, str], *, source: str) -> AssimilationResult:
        from django_borg.models.schemas import SourceField, SourceSchema  # noqa: PLC0415
        from django_borg.resolution import EXTRACT_SENTINEL, resolve_field  # noqa: PLC0415

        source_schema, _ = SourceSchema.objects.get_or_create(name=source)
        cost = AssimilationCost()
        unresolved: list[str] = []
        mapped: dict[str, str] = {}
        extraction_inputs: list[tuple[str, str]] = []

        for src_field_name, src_value in raw_item.items():
            SourceField.objects.get_or_create(schema=source_schema, name=src_field_name)

            if src_field_name in self.extract_from:
                extraction_inputs.append((src_field_name, src_value))
                continue

            field_res = resolve_field(
                source_schema,
                src_field_name,
                self.target_schema,
                ai=self.ai,
                ai_voter=self.ai_voter,
            )
            self._record_cost(field_res, cost)

            if field_res.target == EXTRACT_SENTINEL:
                extraction_inputs.append((src_field_name, src_value))
                continue

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

        self._run_extraction_pass(extraction_inputs, mapped, unresolved, cost)

        return AssimilationResult(
            product=self.target_model(**mapped),
            unresolved=unresolved,
            cost=cost,
        )

    def _run_extraction_pass(
        self,
        extraction_inputs: list[tuple[str, str]],
        mapped: dict[str, str],
        unresolved: list[str],
        cost: AssimilationCost,
    ) -> None:
        for src_field_name, text in extraction_inputs:
            if not text:
                continue

            target_field_names = [
                f.name
                for f in self.target_schema.fields.all()
                if f.name not in mapped
            ]
            if not target_field_names:
                continue

            try:
                extracted = self.ai.extract(
                    text,
                    target_schema=self.target_schema.name,
                    target_fields=target_field_names,
                )
            except Exception:  # noqa: BLE001
                unresolved.append(src_field_name)
                continue

            cost.record_ai()
            cost.record_extraction()

            for target_field_name, raw_value in extracted.items():
                if target_field_name in mapped:
                    continue
                try:
                    target_field = TargetField.objects.get(
                        schema=self.target_schema,
                        name=target_field_name,
                    )
                except TargetField.DoesNotExist:
                    continue
                value = self._resolve_value_or_raw(target_field, raw_value, cost)
                if value is None:
                    continue
                mapped[target_field_name] = value
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_ingestion.py -v`
Expected: 24 passed (18 prior + 6 new).

- [ ] **Step 5: Commit**

```bash
git add django_borg/ingestion.py tests/test_ingestion.py
git commit -m "feat: two-pass assimilate handles extract_from sources"
```

---

## Task 5: Rule-driven extraction trigger

**Files:**
- Modify: `tests/test_ingestion.py`

(no production code change — Task 4's `EXTRACT_SENTINEL` check already routes rule-resolved targets into extraction)

- [ ] **Step 1: Append failing test**

Append to `tests/test_ingestion.py`:

```python
@pytest.mark.django_db
def test_rule_with_extract_sentinel_routes_to_extraction():
    ai = FakeInferencer(
        extract_map={"some blob": {"color": "rotes"}},
        value_map={("color", "rotes"): "red"},
    )
    borg = SchemaAssimilator(target_schema=Product, ai=ai)
    schema = TargetSchema.objects.get(name="Product")
    factories.FieldRuleFactory(
        target_schema=schema,
        source_pattern="caption",
        target=EXTRACT_SENTINEL,
    )

    result = borg.assimilate({"caption": "some blob"}, source="acme")
    assert result.product.color == "red"
    assert result.cost.extraction_calls == 1


@pytest.mark.django_db
def test_rule_extraction_does_not_pollute_field_mapping_table():
    """A DO rule with __extract__ target should not create a FieldMapping row
    just for routing; it stays a rule-only construct."""
    ai = FakeInferencer(
        extract_map={"blob": {"color": "rotes"}},
        value_map={("color", "rotes"): "red"},
    )
    borg = SchemaAssimilator(target_schema=Product, ai=ai)
    schema = TargetSchema.objects.get(name="Product")
    factories.FieldRuleFactory(
        target_schema=schema,
        source_pattern="caption",
        target=EXTRACT_SENTINEL,
    )

    borg.assimilate({"caption": "blob"}, source="acme")
    src = SourceSchema.objects.get(name="acme")
    assert not FieldMapping.objects.filter(source_schema=src, source_field="caption").exists()
```

- [ ] **Step 2: Run — expect pass**

Run: `uv run pytest tests/test_ingestion.py::test_rule_with_extract_sentinel_routes_to_extraction tests/test_ingestion.py::test_rule_extraction_does_not_pollute_field_mapping_table -v`
Expected: 2 passed (Task 4 already wired the sentinel check).

- [ ] **Step 3: Commit**

```bash
git add tests/test_ingestion.py
git commit -m "test: lock rule-driven extraction routing via __extract__ sentinel"
```

---

## Task 6: Public API export

**Files:**
- Modify: `django_borg/__init__.py`
- Modify: `tests/test_public_api.py`

- [ ] **Step 1: Append failing test**

Replace `tests/test_public_api.py` with:

```python
from django_borg import (
    EXTRACT_SENTINEL,
    AssimilationCost,
    AssimilationResult,
    FakeInferencer,
    Inferencer,
    Resolution,
    ResolutionSource,
    SchemaAssimilator,
)


def test_public_api_exports():
    assert SchemaAssimilator is not None
    assert Inferencer is not None
    assert FakeInferencer is not None
    assert AssimilationCost is not None
    assert AssimilationResult is not None
    assert Resolution is not None
    assert ResolutionSource is not None
    assert EXTRACT_SENTINEL == "__extract__"
```

- [ ] **Step 2: Run — expect ImportError**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: FAIL — `cannot import name 'EXTRACT_SENTINEL'`.

- [ ] **Step 3: Export `EXTRACT_SENTINEL` from the package**

Edit `django_borg/__init__.py`. Replace its body:

```python
"""AI-bootstrapped, vote-curated schema mapping for Django."""

from typing import Any

__all__ = [
    "EXTRACT_SENTINEL",
    "AssimilationCost",
    "AssimilationResult",
    "FakeInferencer",
    "Inferencer",
    "Resolution",
    "ResolutionSource",
    "SchemaAssimilator",
]

_LAZY_MODULES = {
    "AssimilationCost": "django_borg.ingestion",
    "AssimilationResult": "django_borg.ingestion",
    "SchemaAssimilator": "django_borg.ingestion",
    "FakeInferencer": "django_borg.ai",
    "Inferencer": "django_borg.ai",
    "Resolution": "django_borg.resolution",
    "ResolutionSource": "django_borg.resolution",
    "EXTRACT_SENTINEL": "django_borg.resolution",
}


def __getattr__(name: str) -> Any:  # noqa: ANN401
    """Lazy attribute access so importing the package doesn't load Django models.

    Django imports app packages during INSTALLED_APPS setup; eagerly importing model code
    here raises AppRegistryNotReady. This dispatch defers each symbol to its submodule.
    """
    module_path = _LAZY_MODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module 'django_borg' has no attribute {name!r}")
    import importlib  # noqa: PLC0415

    module = importlib.import_module(module_path)
    return getattr(module, name)
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add django_borg/__init__.py tests/test_public_api.py
git commit -m "feat: export EXTRACT_SENTINEL from public API"
```

---

## Task 7: Lint, type, and full-suite gate

**Files:** none — verification only.

- [ ] **Step 1: Run ruff**

Run: `uv run ruff check django_borg tests`
Expected: clean. If lint errors, fix in place; commit fixes with `style: ruff fixes`.

- [ ] **Step 2: Run ruff format check**

Run: `uv run ruff format --check django_borg tests`
Expected: clean. If formatting drift, run `uv run ruff format django_borg tests` and commit `style: apply ruff format`.

- [ ] **Step 3: Run mypy**

Run: `uv run mypy django_borg`
Expected: clean. Fix any reported issues; commit fixes with `chore: appease mypy`.

- [ ] **Step 4: Run full pytest suite**

Run: `uv run pytest -q`
Expected: 96 passed (80 from Plan 1 + 4 in test_ai + 12 in test_ingestion). Coverage ≥ 90% on `django_borg/*`.

---

## Task 8: README extraction section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Read current README**

Run: `cat README.md`. Confirm the existing "Quickstart" section ends before "## Documentation".

- [ ] **Step 2: Append an Extraction subsection to the Quickstart**

Insert the following block in `README.md` directly before the line `## Documentation` (i.e. after the existing Quickstart code block and explanation):

```markdown
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
DO rule whose target is `EXTRACT_SENTINEL` ("`__extract__`") — useful when the
choice of extraction source is itself something you want to vote on.
```

- [ ] **Step 3: Sanity-check the snippet imports work**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document extraction in Quickstart"
```

---

## Self-review checklist (run after Task 8)

- [ ] Spec coverage: extraction (mapping type 3) wired end-to-end: AI protocol method (Task 1), trigger (Tasks 3 & 5), orchestration (Task 4), cost (Task 2), API (Task 6), docs (Task 8).
- [ ] No placeholders in this plan.
- [ ] Type names used consistently: `Inferencer.extract`, `EXTRACT_SENTINEL`, `extract_from`, `extraction_calls`, `_run_extraction_pass`.
- [ ] All tasks have failing-test → impl → passing-test → commit rhythm (Task 5 reuses Task 4's wiring with a behavioural test, no impl change — explicitly noted).
- [ ] Direct mappings always win over extraction at the target-field level (Task 4 test `test_assimilate_direct_mapping_wins_over_extraction`).
- [ ] Extraction failures degrade gracefully (`unresolved`, no batch crash).

---

## Out of scope (still — separate plans)

- **`Extraction` Mapping subclass** with its own vote log. Plan 4 (drift) is the natural place to revisit this once we have data on extraction stability.
- **Reviewer UI** for extraction (e.g. "approve this column as an extraction source") — Plan 3.
- **Real Pydantic AI / Instructor adapter** with structured output for `extract` — Plan 5.
