import pytest
from testapp.models import Product

from django_borg.ai import FakeInferencer
from django_borg.ingestion import AssimilationCost, AssimilationResult, SchemaAssimilator
from django_borg.models import (
    FieldMapping,
    Rule,
    SourceSchema,
    TargetField,
    TargetSchema,
    ValueMapping,
    Vote,
    Voter,
)
from django_borg.resolution import EXTRACT_SENTINEL
from tests import factories


@pytest.mark.django_db
def test_init_creates_target_schema_record():
    SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    assert TargetSchema.objects.filter(name="Product").exists()


@pytest.mark.django_db
def test_init_creates_target_fields_for_concrete_columns():
    SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    schema = TargetSchema.objects.get(name="Product")
    names = set(schema.fields.values_list("name", flat=True))
    # 'id' is auto and must be skipped; explicit fields are present.
    assert names == {"title", "color", "size"}


@pytest.mark.django_db
def test_init_marks_choice_fields_as_enum():
    SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    schema = TargetSchema.objects.get(name="Product")
    title = TargetField.objects.get(schema=schema, name="title")
    color = TargetField.objects.get(schema=schema, name="color")
    assert title.is_enum is False
    assert color.is_enum is True


@pytest.mark.django_db
def test_init_creates_default_ai_voter():
    SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    assert Voter.objects.filter(kind=Voter.Kind.AI, identifier="ai").exists()


@pytest.mark.django_db
def test_reinit_is_idempotent():
    SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    assert TargetSchema.objects.filter(name="Product").count() == 1
    assert TargetField.objects.filter(schema__name="Product").count() == 3


def test_assimilation_cost_arithmetic():
    cost = AssimilationCost()
    cost.record_ai()
    cost.record_ai()
    cost.record_deterministic()
    assert cost.ai_calls == 2
    assert cost.deterministic_hits == 1


def test_assimilation_result_carries_product_and_unresolved():
    result = AssimilationResult(
        product=object(),
        unresolved=["mystery_field"],
        cost=AssimilationCost(),
    )
    assert result.unresolved == ["mystery_field"]


@pytest.fixture
def borg(db):
    ai = FakeInferencer(
        field_map={"Farbe": "color", "Titel": "title", "Größe": "size"},
        value_map={
            ("color", "Rot"): "red",
            ("size", "M"): "M",
        },
    )
    return SchemaAssimilator(target_schema=Product, ai=ai)


@pytest.mark.django_db
def test_assimilate_returns_unsaved_product_instance(borg):
    result = borg.assimilate(
        {"Titel": "T-Shirt", "Farbe": "Rot", "Größe": "M"},
        source="acme",
    )
    assert isinstance(result.product, Product)
    assert result.product.pk is None  # unsaved
    assert result.product.title == "T-Shirt"
    assert result.product.color == "red"
    assert result.product.size == "M"


@pytest.mark.django_db
def test_assimilate_creates_source_schema_on_first_use(borg):
    borg.assimilate({"Farbe": "Rot"}, source="acme")
    assert SourceSchema.objects.filter(name="acme").exists()


@pytest.mark.django_db
def test_assimilate_records_cost_for_first_run(borg):
    result = borg.assimilate(
        {"Titel": "T-Shirt", "Farbe": "Rot", "Größe": "M"},
        source="acme",
    )
    # 3 field calls + 2 value calls (title is not enum, no value lookup) = 5 AI calls
    assert result.cost.ai_calls == 5
    assert result.cost.deterministic_hits == 0


@pytest.mark.django_db
def test_assimilate_uses_deterministic_path_after_graduation(borg):
    src = SourceSchema.objects.create(name="acme")
    schema = TargetSchema.objects.get(name="Product")
    color = TargetField.objects.get(schema=schema, name="color")

    fm = FieldMapping.objects.create(
        source_schema=src,
        source_field="Farbe",
        target_schema=schema,
    )
    vm = ValueMapping.objects.create(target_field=color, source_value="Rot")
    reviewer = factories.ReviewerVoterFactory()

    Vote.objects.create(mapping=fm, voter=reviewer, agreed_target="color")
    Vote.objects.create(mapping=vm, voter=reviewer, agreed_target="red")

    result = borg.assimilate({"Farbe": "Rot"}, source="acme")
    assert result.product.color == "red"
    assert result.cost.ai_calls == 0
    assert result.cost.deterministic_hits == 2  # field + value


@pytest.mark.django_db
def test_assimilate_reports_unresolved_when_ai_fails():
    ai = FakeInferencer()  # empty -> AI raises LookupError
    borg = SchemaAssimilator(target_schema=Product, ai=ai)
    result = borg.assimilate({"Mystery": "x"}, source="acme")
    assert result.unresolved == ["Mystery"]
    assert result.product.title == ""  # default


@pytest.mark.django_db
def test_assimilate_skips_blank_source_values(borg):
    result = borg.assimilate({"Titel": "T-Shirt", "Farbe": ""}, source="acme")
    # 'Farbe' is blank -> skip value resolution; field still mapped but value stays blank.
    assert result.product.color == ""
    assert result.product.title == "T-Shirt"


@pytest.mark.django_db
def test_assimilate_blocked_field_skips_assignment(borg):
    schema = TargetSchema.objects.get(name="Product")
    factories.FieldRuleFactory(
        target_schema=schema,
        source_pattern="internal_id",
        polarity=Rule.Polarity.DONT,
        target="",
    )
    result = borg.assimilate({"internal_id": "123", "Titel": "X"}, source="acme")
    assert result.product.title == "X"
    assert "internal_id" in result.unresolved


def test_assimilation_cost_records_extraction():
    cost = AssimilationCost()
    cost.record_extraction()
    cost.record_extraction()
    assert cost.extraction_calls == 2
    assert cost.ai_calls == 0  # extraction call counter is independent


def test_extract_sentinel_value():
    assert EXTRACT_SENTINEL == "__extract__"


@pytest.mark.django_db
def test_assimilator_accepts_extract_from_iterable():
    borg = SchemaAssimilator(
        target_schema=Product,
        ai=FakeInferencer(),
        extract_from=["description", "Beschreibung"],
    )
    assert borg.extract_from == {"description", "Beschreibung"}


@pytest.mark.django_db
def test_assimilator_extract_from_defaults_to_empty():
    borg = SchemaAssimilator(target_schema=Product, ai=FakeInferencer())
    assert borg.extract_from == set()


@pytest.fixture
def borg_with_extract(db):
    ai = FakeInferencer(
        field_map={"Titel": "title"},
        value_map={
            ("color", "rotes"): "red",
            ("size", "M"): "M",
        },
        extract_map={
            "100% Baumwolle, rotes T-Shirt, Größe M": {
                "color": "rotes",
                "size": "M",
            },
        },
    )
    return SchemaAssimilator(
        target_schema=Product,
        ai=ai,
        extract_from=["description"],
    )


@pytest.mark.django_db
def test_assimilate_runs_extraction_for_extract_from_source(borg_with_extract):
    result = borg_with_extract.assimilate(
        {
            "Titel": "T-Shirt",
            "description": "100% Baumwolle, rotes T-Shirt, Größe M",
        },
        source="acme",
    )
    assert result.product.title == "T-Shirt"
    assert result.product.color == "red"
    assert result.product.size == "M"


@pytest.mark.django_db
def test_assimilate_extraction_increments_extraction_calls(borg_with_extract):
    result = borg_with_extract.assimilate(
        {"description": "100% Baumwolle, rotes T-Shirt, Größe M"},
        source="acme",
    )
    assert result.cost.extraction_calls == 1


@pytest.mark.django_db
def test_assimilate_skips_extraction_for_blank_text(borg_with_extract):
    result = borg_with_extract.assimilate(
        {"description": ""},
        source="acme",
    )
    assert result.cost.extraction_calls == 0
    # No AI calls at all -- blank text short-circuits.
    assert result.cost.ai_calls == 0


@pytest.mark.django_db
def test_assimilate_direct_mapping_wins_over_extraction(borg_with_extract):
    # Direct mapping for "color" via FieldMapping + ValueMapping graduation
    schema = TargetSchema.objects.get(name="Product")
    color = TargetField.objects.get(schema=schema, name="color")
    src = SourceSchema.objects.get_or_create(name="acme")[0]
    direct_color_field = FieldMapping.objects.create(
        source_schema=src,
        source_field="Color",
        target_schema=schema,
    )
    color_value = ValueMapping.objects.create(target_field=color, source_value="blau")
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=direct_color_field, voter=reviewer, agreed_target="color")
    Vote.objects.create(mapping=color_value, voter=reviewer, agreed_target="blue")

    result = borg_with_extract.assimilate(
        {
            "Color": "blau",
            "description": "100% Baumwolle, rotes T-Shirt, Größe M",
        },
        source="acme",
    )
    # Direct mapping picks blue; extraction's "rotes -> red" does NOT clobber it.
    assert result.product.color == "blue"
    # Extraction still runs (size needs filling) -- it just respects already-mapped fields.
    assert result.product.size == "M"


@pytest.mark.django_db
def test_assimilate_extraction_failure_marks_unresolved(db):
    ai = FakeInferencer()  # empty extract_map -> raises
    borg = SchemaAssimilator(
        target_schema=Product,
        ai=ai,
        extract_from=["description"],
    )
    result = borg.assimilate({"description": "anything"}, source="acme")
    assert "description" in result.unresolved
    # Pass 1 didn't raise; we just lose the extraction output.
    assert result.product.title == ""


@pytest.mark.django_db
def test_assimilate_extraction_passes_only_unfilled_target_fields(borg_with_extract):
    # Pre-fill 'size' through a graduated value mapping so extraction is asked only for color.
    schema = TargetSchema.objects.get(name="Product")
    size = TargetField.objects.get(schema=schema, name="size")
    src_schema = SourceSchema.objects.get_or_create(name="acme")[0]
    size_field = FieldMapping.objects.create(
        source_schema=src_schema,
        source_field="Größe",
        target_schema=schema,
    )
    size_value = ValueMapping.objects.create(target_field=size, source_value="M")
    reviewer = factories.ReviewerVoterFactory()
    Vote.objects.create(mapping=size_field, voter=reviewer, agreed_target="size")
    Vote.objects.create(mapping=size_value, voter=reviewer, agreed_target="M")

    borg_with_extract.assimilate(
        {"Größe": "M", "description": "100% Baumwolle, rotes T-Shirt, Größe M"},
        source="acme",
    )
    extract_calls = [c for c in borg_with_extract.ai.calls if c[0] == "extract"]
    assert len(extract_calls) == 1
    _, _, _, requested_fields = extract_calls[0]
    assert "size" not in requested_fields
    assert "color" in requested_fields
