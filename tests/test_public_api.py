from django_borg import (
    EXTRACT_SENTINEL,
    AssimilationCost,
    AssimilationResult,
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
