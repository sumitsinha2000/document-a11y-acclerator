from fastapi.testclient import TestClient
import pytest

from backend.app import app


@pytest.fixture(scope="session")
def client():
    return TestClient(app)
