"""Shared test fixtures."""

import pytest
from ulid import ULID


@pytest.fixture()
def sample_ulid() -> ULID:
    return ULID()


@pytest.fixture()
def sample_session_id() -> ULID:
    return ULID()
