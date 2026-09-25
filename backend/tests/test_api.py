from pathlib import Path
from unittest.mock import patch
import pytest

from app.models import GameItem


@pytest.fixture
def mock_fdroid_games():
    return [
        GameItem(
            id="org.game.fdroid1",
            title="FDroid Game 1",
            source="fdroid",
            icon_url="/cache/icon_fdroid.png",
            screenshots=["/cache/screen1.png"],
            description="FDroid test game",
            developer="F-Droid Dev",
            download_url="https://f-droid.org/repo/game1.apk",
            tags=["Games", "Puzzle"],
        )
    ]


@pytest.fixture
def mock_itchio_games():
    return [
        GameItem(
            id="9999",
            title="Itch Game 1",
            source="itchio",
            icon_url="/cache/icon_itch.png",
            screenshots=[],
            description="Itch test game",
            developer="Itch Dev",
            download_url=None,
            tags=["Action", "Indie"],
        )
    ]


def test_root_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "service" in res.json()


def test_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_catalog_fdroid_only(client, mock_fdroid_games):
    with patch("app.main.get_fdroid_games", return_value=mock_fdroid_games):
        res = client.get("/catalog?source=fdroid")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        item = data[0]
        assert item["id"] == "org.game.fdroid1"
        assert item["source"] == "fdroid"
        assert item["download_url"] == "https://f-droid.org/repo/game1.apk"
        # Validate schema keys
        expected_keys = {
            "id", "title", "source", "icon_url", "screenshots",
            "description", "developer", "download_url", "tags"
        }
        assert set(item.keys()) == expected_keys


def test_catalog_itchio_only(client, mock_itchio_games):
    with patch("app.main.scrape_itchio_games", return_value=mock_itchio_games):
        res = client.get("/catalog?source=itchio")
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        item = data[0]
        assert item["id"] == "9999"
        assert item["source"] == "itchio"
        assert item["download_url"] is None
        expected_keys = {
            "id", "title", "source", "icon_url", "screenshots",
            "description", "developer", "download_url", "tags"
        }
        assert set(item.keys()) == expected_keys


def test_catalog_all_sources(client, mock_fdroid_games, mock_itchio_games):
    with patch("app.main.get_fdroid_games", return_value=mock_fdroid_games):
        with patch("app.main.scrape_itchio_games", return_value=mock_itchio_games):
            res = client.get("/catalog")
            assert res.status_code == 200
            data = res.json()
            assert len(data) == 2
            sources = [x["source"] for x in data]
            assert "fdroid" in sources
            assert "itchio" in sources


def test_catalog_with_tag_and_page(client, mock_fdroid_games):
    with patch("app.main.get_fdroid_games", return_value=mock_fdroid_games) as mock_get_fdroid:
        res = client.get("/catalog?source=fdroid&tag=Puzzle&page=2")
        assert res.status_code == 200
        mock_get_fdroid.assert_called_once_with(tag="Puzzle", page=2, page_size=20)


def test_cache_endpoint_serving(client, tmp_path):
    test_img = tmp_path / "sample.png"
    test_img.write_bytes(b"\x89PNG\r\n\x1a\nfakeimage")

    with patch("app.main.get_cached_image_path", return_value=test_img):
        res = client.get("/cache/sample.png")
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/png"
        assert res.headers["cache-control"] == "public, max-age=604800, immutable"
        assert res.content == b"\x89PNG\r\n\x1a\nfakeimage"


def test_cache_endpoint_404(client):
    with patch("app.main.get_cached_image_path", return_value=None):
        res = client.get("/cache/missing.png")
        assert res.status_code == 404
        assert res.json()["detail"] == "Image not found in cache"
