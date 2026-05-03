from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Callable


class _AgentLike(Protocol):
    def run_sync(self, prompt: str, *, output_type: type[BaseModel]) -> Any: ...  # noqa: ANN401


class _FieldChoice(BaseModel):
    target_field: str


class _ValueChoice(BaseModel):
    target_value: str


def _default_target_fields_for(schema_name: str) -> list[str]:
    from django_borg.models import TargetField  # noqa: PLC0415

    return list(
        TargetField.objects.filter(schema__name=schema_name).values_list("name", flat=True),
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


def _default_prompt_for_value(source: str, target_field: str) -> str:
    return (
        f"Canonicalise a supplier value to its target-field equivalent.\n"
        f"Target field: {target_field}\n"
        f"Source value: {source!r}\n"
        f"Reply with the canonical value in `target_value`."
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
        prompt_for_value: Callable[[str, str], str] | None = None,
    ) -> None:
        self.agent = agent
        self.target_fields_for = target_fields_for or _default_target_fields_for
        self.prompt_for_field = prompt_for_field or _default_prompt_for_field
        self.prompt_for_value = prompt_for_value or _default_prompt_for_value

    def map_field(self, source: str, *, target_schema: str) -> str:
        target_fields = self.target_fields_for(target_schema)
        prompt = self.prompt_for_field(source, target_schema, target_fields)
        result = self.agent.run_sync(prompt, output_type=_FieldChoice)
        return result.output.target_field

    def map_value(self, source: str, *, target_field: str) -> str:
        prompt = self.prompt_for_value(source, target_field)
        result = self.agent.run_sync(prompt, output_type=_ValueChoice)
        return result.output.target_value
