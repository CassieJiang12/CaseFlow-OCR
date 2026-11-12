from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, extraction_mode="mock", database_path=tmp_path / "test.sqlite3")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as connection:
        yield connection


@pytest.fixture
def samples():
    return Path(__file__).resolve().parents[1] / "samples"

