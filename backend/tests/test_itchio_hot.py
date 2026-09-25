from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.itchio_hot import (
    build_itchio_hot_url,
    parse_and_verify_hot_games_offline,
    scrape_itchio_hot_games,
    verify_game_has_apk,
)


@pytest.fixture
def itchio_game_with_apk_html(fixtures_dir) -> str:
    with open(fixtures_dir / "itchio_game_with_apk.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def itchio_game_without_apk_html(fixtures_dir) -> str:
    with open(fixtures_dir / "itchio_game_without_apk.html", "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture
def itchio_hot_games_html(fixtures_dir) -> str:
    with open(fixtures_dir / "itchio_hot_games.html", "r", encoding="utf-8") as f:
        return f.read()


def test_build_itchio_hot_url():
    assert build_itchio_hot_url() == "https://itch.io/games/new-and-popular?page=1"
    assert build_itchio_hot_url(page=3) == "https://itch.io/games/new-and-popular?page=3"
    assert build_itchio_hot_url(tag="Action", page=2) == "https://itch.io/games/tag-action/new-and-popular?page=2"


def test_verify_game_has_apk_true(itchio_game_with_apk_html):
    has_apk, apk_name = verify_game_has_apk(itchio_game_with_apk_html)
    assert has_apk is True
    assert apk_name is not None
    assert apk_name.lower().endswith(".apk")
    assert "poprise" in apk_name.lower()


def test_verify_game_has_apk_false(itchio_game_without_apk_html):
    has_apk, apk_name = verify_game_has_apk(itchio_game_without_apk_html)
    assert has_apk is False
    assert apk_name is None


def test_verify_game_has_apk_empty():
    assert verify_game_has_apk("") == (False, None)
    assert verify_game_has_apk("<html><body><div>No downloads here</div></body></html>") == (False, None)


def test_parse_and_verify_hot_games_discards_non_apk(
    itchio_hot_games_html,
    itchio_game_with_apk_html,
    itchio_game_without_apk_html,
):
    # Simulated game page resolver:
    # First candidate gets the APK HTML; all other candidates get the non-APK HTML
    call_count = 0

    def mock_page_resolver(url: str) -> str:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return itchio_game_with_apk_html
        return itchio_game_without_apk_html

    verified_games = parse_and_verify_hot_games_offline(
        hot_listing_html=itchio_hot_games_html,
        game_html_provider=mock_page_resolver,
    )

    # Exactly 1 game should survive the APK filter
    assert len(verified_games) == 1
    survivor = verified_games[0]
    assert survivor.source == "itchio"
    assert "Android" in survivor.tags
    assert "Hot" in survivor.tags


def test_catalog_hot_endpoint_api(client):
    mock_game = MagicMock()
    mock_game.model_dump.return_value = {
        "id": "1234",
        "title": "Verified Android Game",
        "source": "itchio",
        "icon_url": "/cache/icon.png",
        "screenshots": [],
        "description": "Android APK verified",
        "developer": "Dev",
        "download_url": None,
        "tags": ["Android", "Hot"],
    }
    # To satisfy Pydantic response_model serialization:
    from app.models import GameItem
    real_game = GameItem(
        id="1234",
        title="Verified Android Game",
        source="itchio",
        icon_url="/cache/icon.png",
        screenshots=[],
        description="Android APK verified",
        developer="Dev",
        download_url=None,
        tags=["Android", "Hot"],
    )

    with patch("app.main.scrape_itchio_hot_games", return_value=[real_game]):
        res = client.get("/catalog?section=hot")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["title"] == "Verified Android Game"
        assert "Android" in data[0]["tags"]

        res2 = client.get("/catalog/hot")
        assert res2.status_code == 200
        assert res2.json()[0]["title"] == "Verified Android Game"
