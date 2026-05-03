from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Callable


class _AgentLike(Protocol):
    def run_sync(self, prompt: str, *, output_type: type[BaseModel]) -> Any: ...  # noqa: ANN401


class _FieldChoice(BaseModel):
    target_field: str


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
