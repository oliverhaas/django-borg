# django-borg Reference AI Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a reference `Inferencer` implementation — `StructuredOutputInferencer` — that wraps any agent exposing `agent.run_sync(prompt, *, output_type=PydanticModel)` (Pydantic AI's `Agent` matches verbatim) and translates the protocol's three calls into prompts + structured-output calls.

**Architecture:** Duck-typed against `agent.run_sync(...) -> result.output`. No hard dependency on `pydantic-ai` — the adapter only requires `pydantic` (for the BaseModel response shapes), available as the `[adapters]` optional extra. Consumers using Pydantic AI, Instructor, or a hand-rolled OpenAI structured-output client just need an object that exposes the same `run_sync` shape. The adapter is intentionally an example rather than a black box, so the prompt strings are short, English, and easy to override via constructor injection.

**Tech Stack:** Pydantic ≥ 2 (optional extra), the existing `Inferencer` protocol, the existing django-borg core engine.

---

## What this plan does NOT deliver

- **No specific LLM client** — no `openai`, `anthropic`, or `pydantic-ai` runtime dep. The reference adapter is vendor-agnostic via duck-typing.
- **No async API** — `Inferencer` is sync; this stays sync.
- **No prompt-engineering library** — prompts are plain f-strings. Override via constructor for nuance.
- **No streaming** — single-shot structured outputs only.
- **No retry / rate-limit handling** — the wrapped agent does that. The adapter just lets exceptions bubble; resolution code already catches them.

## File layout impacted

```
django_borg/
  adapters/
    __init__.py              # NEW - re-exports
    structured_output.py     # NEW - StructuredOutputInferencer + response models
  __init__.py                # +StructuredOutputInferencer export

tests/
  test_adapters/
    __init__.py              # NEW
    test_structured_output.py # NEW - hand-rolled FakeAgent
README.md                    # +Reference adapter section
pyproject.toml               # +[project.optional-dependencies] adapters = ["pydantic>=2"]
                              # +pydantic in dev group for testing
```

## Key design decisions (locked in this plan)

- **Duck-typed agent.** The constructor accepts any object exposing `run_sync(prompt: str, *, output_type: type[BaseModel]) -> Any` where the return value has a `.output` attribute of type `output_type`. Pydantic AI's `Agent` matches without a shim. `agent.run_sync` is sync; if your underlying client is async, wrap it before passing.
- **`pydantic` is an optional dependency** declared under `[project.optional-dependencies] adapters`. Importing `django_borg.adapters.structured_output` without pydantic installed raises a clear `ImportError`. The core package never imports adapters.
- **Three response models**, one per `Inferencer` method, declared inside the adapter module so consumers don't need to subclass anything: `_FieldChoice(target_field: str)`, `_ValueChoice(target_value: str)`, and `_ExtractedFields(values: dict[str, str])`. Underscore prefix because they're implementation detail — consumers shouldn't depend on their shape.
- **Schema field discovery** for `map_field` and `extract` uses a callable injected at construction: `target_fields_for: Callable[[str], list[str]]`. Default queries Django (`TargetField.objects.filter(schema__name=...)`), so most consumers don't supply one. Tests pass a fixed list to avoid DB roundtrips.
- **Prompts are constructor-overridable**, not module-level constants. Each method has a corresponding `prompt_for_*` callable: `prompt_for_field`, `prompt_for_value`, `prompt_for_extract`. Defaults are bundled; the adapter calls `self.prompt_for_field(source, target_schema, target_fields)` and so on. Override one to tune behaviour for a specific provider, leave the rest.
- **`extract` returns `dict[str, str]`** — the protocol's contract. The internal response model uses a single `values` dict to avoid dynamic Pydantic model creation per call (which would break caching and is fragile across pydantic versions). The adapter filters the returned dict to `target_fields` before returning.
- **Errors propagate.** If the agent raises (rate limit, network, parse error), the adapter doesn't swallow it — the existing resolution code in `django_borg.resolution` catches broadly and reports `unresolved`.

## Settings

No new settings. The adapter is configured entirely through its constructor.

---

## Task 1: Optional `adapters` extra + `StructuredOutputInferencer.map_field`

**Files:**
- Modify: `pyproject.toml`
- Create: `django_borg/adapters/__init__.py`
- Create: `django_borg/adapters/structured_output.py`
- Create: `tests/test_adapters/__init__.py`
- Create: `tests/test_adapters/test_structured_output.py`

- [ ] **Step 1: Add `pydantic` to deps**

Edit `pyproject.toml`. Add the optional-dependencies block right after the `[project.urls]` block (before `[dependency-groups]`):

```toml
[project.optional-dependencies]
adapters = ["pydantic>=2,<3"]
```

In `[dependency-groups] dev`, add `pydantic` so test suite can exercise the adapter. Place it alphabetically:

```toml
  "pydantic==2.11.9",
```

(Adjust the version to whatever `uv add` resolves to; the constraint above is permissive.)

Run:

```bash
uv sync --extra adapters
```

Expected: pydantic gets installed, `uv.lock` updates.

- [ ] **Step 2: Create the adapters package skeleton**

Create `django_borg/adapters/__init__.py`:

```python
"""Reference adapters wiring django-borg's Inferencer protocol to LLM clients.

Adapters live under their own optional extras to keep the core package free of
LLM-specific dependencies. Install via:

    pip install django-borg[adapters]
"""
```

- [ ] **Step 3: Create `tests/test_adapters/__init__.py`**

```python
```

(empty file)

- [ ] **Step 4: Write failing tests for `map_field`**

Create `tests/test_adapters/test_structured_output.py`:

```python
import pytest
from pydantic import BaseModel

from django_borg.adapters.structured_output import StructuredOutputInferencer


class FakeRunResult:
    def __init__(self, output):
        self.output = output


class FakeAgent:
    """Duck-types pydantic-ai's Agent: run_sync(prompt, *, output_type) -> result."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def run_sync(self, prompt: str, *, output_type: type[BaseModel]):
        self.calls.append((prompt, output_type))
        return FakeRunResult(self.handler(prompt, output_type))


def test_map_field_returns_agent_choice():
    def handler(prompt: str, output_type: type[BaseModel]):
        assert "Farbe" in prompt
        assert "color" in prompt
        return output_type(target_field="color")

    agent = FakeAgent(handler)
    inferencer = StructuredOutputInferencer(
        agent=agent,
        target_fields_for=lambda _: ["title", "color", "size"],
    )
    assert inferencer.map_field("Farbe", target_schema="Product") == "color"


def test_map_field_lists_target_fields_in_prompt():
    def handler(prompt: str, output_type: type[BaseModel]):
        return output_type(target_field="color")

    agent = FakeAgent(handler)
    inferencer = StructuredOutputInferencer(
        agent=agent,
        target_fields_for=lambda _: ["title", "color"],
    )
    inferencer.map_field("Farbe", target_schema="Product")
    prompt, _ = agent.calls[0]
    assert "title" in prompt
    assert "color" in prompt
    assert "Product" in prompt


def test_map_field_propagates_agent_exceptions():
    def handler(*args, **kwargs):
        raise RuntimeError("rate limit")

    agent = FakeAgent(handler)
    inferencer = StructuredOutputInferencer(
        agent=agent,
        target_fields_for=lambda _: ["color"],
    )
    with pytest.raises(RuntimeError, match="rate limit"):
        inferencer.map_field("Farbe", target_schema="Product")


def test_custom_prompt_for_field_is_used():
    def handler(prompt: str, output_type: type[BaseModel]):
        return output_type(target_field="color")

    agent = FakeAgent(handler)
    inferencer = StructuredOutputInferencer(
        agent=agent,
        target_fields_for=lambda _: ["color"],
        prompt_for_field=lambda source, schema, fields: f"CUSTOM {source} {schema} {fields}",
    )
    inferencer.map_field("Farbe", target_schema="Product")
    prompt, _ = agent.calls[0]
    assert prompt.startswith("CUSTOM ")
```

- [ ] **Step 5: Run — expect ImportError**

Run: `uv run pytest tests/test_adapters/test_structured_output.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'django_borg.adapters.structured_output'`.

- [ ] **Step 6: Implement `StructuredOutputInferencer.map_field`**

Create `django_borg/adapters/structured_output.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Callable


class _AgentLike(Protocol):
    def run_sync(self, prompt: str, *, output_type: type[BaseModel]): ...


class _FieldChoice(BaseModel):
    target_field: str


def _default_target_fields_for(schema_name: str) -> list[str]:
    from django_borg.models import TargetField  # noqa: PLC0415

    return list(
        TargetField.objects.filter(schema__name=schema_name)
        .values_list("name", flat=True),
    )


def _default_prompt_for_field(
    source: str,
    target_schema: str,
    target_fields: list[str],
) -> str:
    return (
        f"You are mapping supplier columns to a canonical schema.\n"
        f"Target schema: {target_schema}\n"
        f"Target fields: {', '.join(target_fields)}\n"
        f"Pick the single best target field for the source column {source!r}.\n"
        f"Reply with the chosen field name in `target_field`."
    )


class StructuredOutputInferencer:
    """Reference Inferencer that delegates to a structured-output agent.

    Compatible with any agent exposing
    ``run_sync(prompt, *, output_type=BaseModel) -> result_with_output_attr``.
    Pydantic AI's ``Agent`` matches verbatim; Instructor / raw OpenAI clients
    can be wrapped in ten lines.
    """

    def __init__(
        self,
        *,
        agent: _AgentLike,
        target_fields_for: Callable[[str], list[str]] | None = None,
        prompt_for_field: Callable[[str, str, list[str]], str] | None = None,
    ) -> None:
        self.agent = agent
        self.target_fields_for = target_fields_for or _default_target_fields_for
        self.prompt_for_field = prompt_for_field or _default_prompt_for_field

    def map_field(self, source: str, *, target_schema: str) -> str:
        target_fields = self.target_fields_for(target_schema)
        prompt = self.prompt_for_field(source, target_schema, target_fields)
        result = self.agent.run_sync(prompt, output_type=_FieldChoice)
        return result.output.target_field
```

- [ ] **Step 7: Run — expect pass**

Run: `uv run pytest tests/test_adapters/test_structured_output.py -v`
Expected: 4 passed.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock django_borg/adapters/ tests/test_adapters/
git commit -m "feat: add StructuredOutputInferencer with map_field and adapters extra"
```

---

## Task 2: `map_value`

**Files:**
- Modify: `django_borg/adapters/structured_output.py`
- Modify: `tests/test_adapters/test_structured_output.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_adapters/test_structured_output.py`:

```python
def test_map_value_returns_agent_choice():
    def handler(prompt: str, output_type: type[BaseModel]):
        assert "Rot" in prompt
        assert "color" in prompt
        return output_type(target_value="red")

    agent = FakeAgent(handler)
    inferencer = StructuredOutputInferencer(
        agent=agent,
        target_fields_for=lambda _: ["color"],
    )
    assert inferencer.map_value("Rot", target_field="color") == "red"


def test_custom_prompt_for_value_is_used():
    def handler(prompt: str, output_type: type[BaseModel]):
        return output_type(target_value="red")

    agent = FakeAgent(handler)
    inferencer = StructuredOutputInferencer(
        agent=agent,
        target_fields_for=lambda _: ["color"],
        prompt_for_value=lambda source, target_field: f"VALUE {source} {target_field}",
    )
    inferencer.map_value("Rot", target_field="color")
    prompt, _ = agent.calls[0]
    assert prompt.startswith("VALUE ")
```

- [ ] **Step 2: Run — expect AttributeError**

Run: `uv run pytest tests/test_adapters/test_structured_output.py -v`
Expected: 2 new failures — `'StructuredOutputInferencer' object has no attribute 'map_value'`.

- [ ] **Step 3: Extend `StructuredOutputInferencer`**

Edit `django_borg/adapters/structured_output.py`. Add a new response model and a default prompt below the existing `_FieldChoice`:

```python
class _ValueChoice(BaseModel):
    target_value: str


def _default_prompt_for_value(source: str, target_field: str) -> str:
    return (
        f"Canonicalise a supplier value to its target-field equivalent.\n"
        f"Target field: {target_field}\n"
        f"Source value: {source!r}\n"
        f"Reply with the canonical value in `target_value`."
    )
```

Update the constructor signature and body:

```python
    def __init__(
        self,
        *,
        agent: _AgentLike,
        target_fields_for: Callable[[str], list[str]] | None = None,
        prompt_for_field: Callable[[str, str, list[str]], str] | None = None,
        prompt_for_value: Callable[[str, str], str] | None = None,
    ) -> None:
        self.agent = agent
        self.target_fields_for = target_fields_for or _default_target_fields_for
        self.prompt_for_field = prompt_for_field or _default_prompt_for_field
        self.prompt_for_value = prompt_for_value or _default_prompt_for_value
```

Add the `map_value` method below `map_field`:

```python
    def map_value(self, source: str, *, target_field: str) -> str:
        prompt = self.prompt_for_value(source, target_field)
        result = self.agent.run_sync(prompt, output_type=_ValueChoice)
        return result.output.target_value
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_adapters/test_structured_output.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add django_borg/adapters/structured_output.py tests/test_adapters/test_structured_output.py
git commit -m "feat: StructuredOutputInferencer.map_value"
```

---

## Task 3: `extract`

**Files:**
- Modify: `django_borg/adapters/structured_output.py`
- Modify: `tests/test_adapters/test_structured_output.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_adapters/test_structured_output.py`:

```python
def test_extract_returns_filtered_dict():
    def handler(prompt: str, output_type: type[BaseModel]):
        return output_type(values={"color": "rotes", "size": "M", "noise": "ignored"})

    agent = FakeAgent(handler)
    inferencer = StructuredOutputInferencer(
        agent=agent,
        target_fields_for=lambda _: ["color", "size", "title"],
    )
    out = inferencer.extract(
        "100% Baumwolle, rotes T-Shirt, Größe M",
        target_schema="Product",
        target_fields=["color", "size"],
    )
    # 'noise' is dropped because it isn't in target_fields
    assert out == {"color": "rotes", "size": "M"}


def test_extract_passes_target_fields_to_prompt():
    def handler(prompt: str, output_type: type[BaseModel]):
        return output_type(values={})

    agent = FakeAgent(handler)
    inferencer = StructuredOutputInferencer(
        agent=agent,
        target_fields_for=lambda _: [],
    )
    inferencer.extract("text", target_schema="Product", target_fields=["color", "size"])
    prompt, _ = agent.calls[0]
    assert "color" in prompt
    assert "size" in prompt


def test_custom_prompt_for_extract_is_used():
    def handler(prompt: str, output_type: type[BaseModel]):
        return output_type(values={})

    agent = FakeAgent(handler)
    inferencer = StructuredOutputInferencer(
        agent=agent,
        target_fields_for=lambda _: [],
        prompt_for_extract=lambda text, schema, fields: f"EX {text} {schema} {fields}",
    )
    inferencer.extract("blob", target_schema="Product", target_fields=["color"])
    prompt, _ = agent.calls[0]
    assert prompt.startswith("EX ")
```

- [ ] **Step 2: Run — expect AttributeError**

Run: `uv run pytest tests/test_adapters/test_structured_output.py -v`
Expected: 3 new failures.

- [ ] **Step 3: Extend `StructuredOutputInferencer`**

Edit `django_borg/adapters/structured_output.py`. Add a response model and prompt default below `_default_prompt_for_value`:

```python
class _ExtractedFields(BaseModel):
    values: dict[str, str]


def _default_prompt_for_extract(
    text: str,
    target_schema: str,
    target_fields: list[str],
) -> str:
    return (
        f"Extract structured values from unstructured supplier text.\n"
        f"Target schema: {target_schema}\n"
        f"Fields to extract: {', '.join(target_fields)}\n"
        f"Source text: {text!r}\n"
        f"Reply with a JSON object under `values`. Each key is one of the\n"
        f"requested fields; each value is the extracted raw string. Omit fields\n"
        f"you cannot extract."
    )
```

Update the constructor:

```python
    def __init__(
        self,
        *,
        agent: _AgentLike,
        target_fields_for: Callable[[str], list[str]] | None = None,
        prompt_for_field: Callable[[str, str, list[str]], str] | None = None,
        prompt_for_value: Callable[[str, str], str] | None = None,
        prompt_for_extract: Callable[[str, str, list[str]], str] | None = None,
    ) -> None:
        self.agent = agent
        self.target_fields_for = target_fields_for or _default_target_fields_for
        self.prompt_for_field = prompt_for_field or _default_prompt_for_field
        self.prompt_for_value = prompt_for_value or _default_prompt_for_value
        self.prompt_for_extract = prompt_for_extract or _default_prompt_for_extract
```

Add the `extract` method below `map_value`:

```python
    def extract(
        self,
        text: str,
        *,
        target_schema: str,
        target_fields: list[str],
    ) -> dict[str, str]:
        prompt = self.prompt_for_extract(text, target_schema, target_fields)
        result = self.agent.run_sync(prompt, output_type=_ExtractedFields)
        requested = set(target_fields)
        return {k: v for k, v in result.output.values.items() if k in requested}
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_adapters/test_structured_output.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add django_borg/adapters/structured_output.py tests/test_adapters/test_structured_output.py
git commit -m "feat: StructuredOutputInferencer.extract"
```

---

## Task 4: Public API + lint/type + README

**Files:**
- Modify: `django_borg/__init__.py`
- Modify: `tests/test_public_api.py`
- Modify: `README.md`

- [ ] **Step 1: Append failing exports test**

Edit `tests/test_public_api.py`. Replace the import block at the top with:

```python
from django_borg import (
    EXTRACT_SENTINEL,
    AssimilationCost,
    AssimilationResult,
    DriftRunResult,
    DriftRunner,
    FakeInferencer,
    Inferencer,
    Resolution,
    ResolutionSource,
    SchemaAssimilator,
    StructuredOutputInferencer,
)
```

Append a new test below the existing ones:

```python
def test_structured_output_inferencer_export():
    assert StructuredOutputInferencer is not None
```

- [ ] **Step 2: Run — expect ImportError**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: FAIL — `cannot import name 'StructuredOutputInferencer'`.

- [ ] **Step 3: Wire the lazy export**

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
    "StructuredOutputInferencer",
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
    "StructuredOutputInferencer": "django_borg.adapters.structured_output",
}
```

- [ ] **Step 4: Run — expect pass**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run ruff, format, mypy, full suite**

```bash
uv run ruff check django_borg tests
uv run ruff format --check django_borg tests
uv run mypy django_borg
uv run pytest -q
```

Expected: all clean. Pytest: 151 passed (142 prior + 9 adapter tests). Coverage ≥ 90%.

- [ ] **Step 6: Append README section**

Insert in `README.md` immediately before the line `## Documentation`:

```markdown
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
```

- [ ] **Step 7: Sanity-check imports**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: 3 passed.

- [ ] **Step 8: Commit**

```bash
git add django_borg/__init__.py tests/test_public_api.py README.md
git commit -m "feat: export StructuredOutputInferencer and document reference adapter"
```

---

## Self-review checklist (run after Task 4)

- [ ] Reference adapter ships — `StructuredOutputInferencer` (Tasks 1–3).
- [ ] Vendor-agnostic — duck-typed agent, no `pydantic-ai` / `openai` runtime dep.
- [ ] `pydantic` is opt-in via the `[adapters]` extra.
- [ ] All three Inferencer methods covered (`map_field`, `map_value`, `extract`).
- [ ] Prompt and field-discovery logic overridable per-method via constructor.
- [ ] No placeholders.
- [ ] Type/name consistency: `StructuredOutputInferencer`, `target_fields_for`, `prompt_for_field`, `prompt_for_value`, `prompt_for_extract`.

---

## Out of scope (still — separate plans)

- **Async adapter** — would require an async `Inferencer` protocol. Revisit when ingestion goes async.
- **Streaming structured output** — single-shot responses cover the use case.
- **Vendor-specific adapters** (Pydantic AI–native, Instructor–native, raw OpenAI) — the duck-typed approach makes these easy to add later if a consumer needs vendor-specific tuning.
