import pytest

from tests import factories


@pytest.mark.django_db
def test_field_mapping_factory_creates_mapping():
    mapping = factories.FieldMappingFactory()
    assert mapping.pk is not None


@pytest.mark.django_db
def test_vote_factory_links_mapping():
    mapping = factories.FieldMappingFactory()
    vote = factories.VoteFactory(mapping=mapping, agreed_target="color")
    assert vote.mapping == mapping
