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
