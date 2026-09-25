import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def fdroid_sample_data(fixtures_dir) -> dict:
    with open(fixtures_dir / "fdroid_sample.json", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def itchio_games_html(fixtures_dir) -> str:
    with open(fixtures_dir / "itchio_games.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def itchio_tag_action_html(fixtures_dir) -> str:
    with open(fixtures_dir / "itchio_tag_action.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def itchio_malformed_html(fixtures_dir) -> str:
    with open(fixtures_dir / "itchio_malformed.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
