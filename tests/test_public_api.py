from django_borg import (
    EXTRACT_SENTINEL,
    AssimilationCost,
    AssimilationResult,
    DriftRunner,
    DriftRunResult,
    FakeInferencer,
    Inferencer,
    Resolution,
    ResolutionSource,
    SchemaAssimilator,
)


def test_public_api_exports():
    assert SchemaAssimilator is not None
    assert Inferencer is not None
    assert FakeInferencer is not None
    assert AssimilationCost is not None
    assert AssimilationResult is not None
    assert Resolution is not None
    assert ResolutionSource is not None
    assert EXTRACT_SENTINEL == "__extract__"


def test_drift_exports():
    assert DriftRunner is not None
    assert DriftRunResult is not None
