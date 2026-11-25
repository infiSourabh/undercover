from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "undercover.sqlite"


@pytest.fixture
def app(db_path: Path):
    return create_app(db_path)


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)
