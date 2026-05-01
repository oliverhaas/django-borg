"""AI-bootstrapped, vote-curated schema mapping for Django."""

from typing import Any

__all__ = [
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
