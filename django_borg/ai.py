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
        requested = set(target_fields)
        return {k: v for k, v in full.items() if k in requested}
