import pytest
from testapp.models import Product

from django_borg.ai import FakeInferencer
from django_borg.drift import DriftRunner, DriftRunResult
from django_borg.models import FieldMapping, SourceSchema, TargetSchema, Vote
from tests import factories


@pytest.fixture
def graduated_field_mapping(db):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=tgt,
    )
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="color")
    fm.refresh_from_db()
    assert fm.confidence >= 0.9
    assert fm.total_weight >= 5
    return fm


@pytest.mark.django_db
def test_drift_runner_revotes_graduated_field_mapping(graduated_field_mapping):
    ai = FakeInferencer(field_map={"Farbe": "color"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run()
    assert isinstance(result, DriftRunResult)
    assert result.field_mappings_revoted == 1
    assert graduated_field_mapping.votes.filter(voter__kind="ai").count() == 1


@pytest.mark.django_db
def test_drift_runner_skips_ungraduated_field_mapping(db):
    src = SourceSchema.objects.create(name="acme")
    tgt = TargetSchema.objects.create(name="Product")
    FieldMapping.objects.create(
        source_schema=src,
        source_field="Untouched",
        target_schema=tgt,
    )  # zero votes -> not graduated
    ai = FakeInferencer(field_map={"Untouched": "title"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run()
    assert result.field_mappings_revoted == 0
    assert ai.calls == []


@pytest.mark.django_db
def test_drift_runner_records_ai_failure(graduated_field_mapping):
    ai = FakeInferencer()  # empty -> raises LookupError
    runner = DriftRunner(target_schema=Product, ai=ai)
    result = runner.run()
    assert result.field_mappings_revoted == 0
    assert result.skipped_ai_failure == 1


@pytest.mark.django_db
def test_drift_runner_disagreement_drops_confidence(graduated_field_mapping):
    """Initial state: 1 reviewer vote (weight 100) for 'color', confidence=1.0.
    Drift run produces an AI vote for 'hue' (weight 1) -> confidence drops to 100/101.
    """
    ai = FakeInferencer(field_map={"Farbe": "hue"})
    runner = DriftRunner(target_schema=Product, ai=ai)
    runner.run()
    graduated_field_mapping.refresh_from_db()
    assert graduated_field_mapping.current_target == "color"  # reviewer still wins
    assert graduated_field_mapping.confidence == pytest.approx(100 / 101)
