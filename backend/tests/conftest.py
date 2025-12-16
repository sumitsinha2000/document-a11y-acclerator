from fastapi.testclient import TestClient
import pytest


@pytest.fixture(scope="session")
def client():
    # Import lazily so tests that don't hit the API can avoid heavy dependencies.
    from backend.app import app

    return TestClient(app)
