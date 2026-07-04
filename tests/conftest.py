"""Shared pytest fixtures.

Network is always mocked; no test performs a real upstream call (see repo instructions).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from channel_relay.main import create_app


@pytest.fixture
def client() -> TestClient:
    """A TestClient bound to a fresh app instance."""
    return TestClient(create_app())
