"""Pytest configuration."""

import pytest

from tests import factories


@pytest.fixture
def ai_voter(db):
    return factories.AiVoterFactory()


@pytest.fixture
def reviewer_voter(db):
    return factories.ReviewerVoterFactory()
