import pytest

from django_borg.ai import FakeInferencer, Inferencer


def test_fake_inferencer_satisfies_protocol():
    fake = FakeInferencer(field_map={"Farbe": "color"}, value_map={("color", "Rot"): "red"})
    assert isinstance(fake, Inferencer)


def test_fake_inferencer_map_field_returns_configured_value():
    fake = FakeInferencer(field_map={"Farbe": "color"})
    assert fake.map_field("Farbe", target_schema="Product") == "color"


def test_fake_inferencer_map_field_raises_on_unknown():
    fake = FakeInferencer()
    with pytest.raises(LookupError):
        fake.map_field("Unbekannt", target_schema="Product")


def test_fake_inferencer_map_value_returns_configured_value():
    fake = FakeInferencer(value_map={("color", "Rot"): "red"})
    assert fake.map_value("Rot", target_field="color") == "red"


def test_fake_inferencer_records_calls():
    fake = FakeInferencer(field_map={"Farbe": "color"})
    fake.map_field("Farbe", target_schema="Product")
    fake.map_field("Farbe", target_schema="Product")
    assert fake.calls == [
        ("map_field", "Farbe", "Product"),
        ("map_field", "Farbe", "Product"),
    ]


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
