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
