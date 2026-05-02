"""Pytest configuration."""

import pytest
from django.test import Client

from tests import factories


@pytest.fixture
def ai_voter(db):
    return factories.AiVoterFactory()


@pytest.fixture
def reviewer_voter(db):
    return factories.ReviewerVoterFactory()


@pytest.fixture
def admin_user(db):
    return factories.UserFactory()


@pytest.fixture
def admin_client(admin_user):
    client = Client()
    client.force_login(admin_user)
    return client
