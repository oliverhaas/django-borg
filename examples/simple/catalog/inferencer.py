"""A pre-loaded FakeInferencer that pretends to know German -> English mappings.

Swap this for ``StructuredOutputInferencer(agent=Agent("openai:gpt-4o"))``
(``pip install django-borg[adapters] pydantic-ai``) for a real LLM round-trip.
"""

from django_borg import FakeInferencer

DEMO_AI = FakeInferencer(
    field_map={
        "Titel": "title",
        "Farbe": "color",
        "Größe": "size",
        "Beschreibung": "description",
    },
    value_map={
        ("color", "Rot"): "red",
        ("color", "Blau"): "blue",
        ("color", "Schwarz"): "black",
        ("color", "Weiß"): "white",
        ("color", "Grün"): "green",
        ("size", "XS"): "XS",
        ("size", "S"): "S",
        ("size", "M"): "M",
        ("size", "L"): "L",
        ("size", "XL"): "XL",
    },
    extract_map={
        "100% Baumwolle, schwarzer Hoodie, Größe XL": {
            "color": "Schwarz",
            "size": "XL",
        },
        "Premium Polo, weiß, M, leichte Baumwolle": {
            "color": "Weiß",
            "size": "M",
        },
    },
)
