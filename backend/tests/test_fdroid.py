from unittest.mock import patch
import pytest

from app.fdroid import (
    get_fdroid_games,
    parse_fdroid_index,
    parse_fdroid_package,
    save_cached_fdroid_games,
)
from app.models import GameItem


def test_parse_fdroid_filters_non_games(fdroid_sample_data):
    games = parse_fdroid_index(fdroid_sample_data)
    pkg_ids = [g.id for g in games]

    # Games should be included
    assert "org.antigravity.game2048" in pkg_ids
    assert "com.example.actiongame" in pkg_ids
    assert "org.minimal.chess" in pkg_ids

    # Non-games must be excluded
    assert "org.nonprofit.newsreader" not in pkg_ids
    assert len(games) == 3


def test_parse_fdroid_package_details(fdroid_sample_data):
    pkg_data = fdroid_sample_data["packages"]["org.antigravity.game2048"]
    item = parse_fdroid_package("org.antigravity.game2048", pkg_data)

    assert item is not None
    assert item.id == "org.antigravity.game2048"
    assert item.title == "2048 Open Source"
    assert item.source == "fdroid"
    assert item.developer == "Gabriele Cirulli"
    assert "2048 puzzle game" in item.description
    assert item.icon_url is not None
    assert item.icon_url.startswith("/cache/")
    assert len(item.screenshots) == 2
    assert all(s.startswith("/cache/") for s in item.screenshots)
    assert item.download_url == "https://f-droid.org/repo/org.antigravity.game2048_100.apk"
    assert "Games" in item.tags
    assert "Puzzle" in item.tags


def test_parse_fdroid_selects_latest_version(fdroid_sample_data):
    pkg_data = fdroid_sample_data["packages"]["com.example.actiongame"]
    item = parse_fdroid_package("com.example.actiongame", pkg_data)

    assert item is not None
    # Version v2 was added at timestamp 1682000000000 > v1 (1681000000000)
    assert item.download_url == "https://f-droid.org/repo/com.example.actiongame_20.apk"
    assert "Action" in item.tags


def test_parse_fdroid_missing_version_and_icon(fdroid_sample_data):
    pkg_data = fdroid_sample_data["packages"]["org.minimal.chess"]
    item = parse_fdroid_package("org.minimal.chess", pkg_data)

    assert item is not None
    assert item.id == "org.minimal.chess"
    assert item.title == "Minimal Chess"
    assert item.icon_url is None
    assert item.download_url is None
    assert item.screenshots == []


def test_get_fdroid_games_tag_filtering(fdroid_sample_data):
    games = parse_fdroid_index(fdroid_sample_data)

    with patch("app.fdroid.load_cached_fdroid_games", return_value=[g.model_dump() for g in games]):
        action_games = get_fdroid_games(tag="Action")
        assert len(action_games) == 1
        assert action_games[0].id == "com.example.actiongame"

        puzzle_games = get_fdroid_games(tag="puzzle")
        assert len(puzzle_games) == 1
        assert puzzle_games[0].id == "org.antigravity.game2048"

        nonexistent = get_fdroid_games(tag="NonExistentCategory")
        assert len(nonexistent) == 0


def test_get_fdroid_games_pagination(fdroid_sample_data):
    games = parse_fdroid_index(fdroid_sample_data)

    with patch("app.fdroid.load_cached_fdroid_games", return_value=[g.model_dump() for g in games]):
        page1 = get_fdroid_games(page=1, page_size=2)
        assert len(page1) == 2
        assert page1[0].id == games[0].id
        assert page1[1].id == games[1].id

        page2 = get_fdroid_games(page=2, page_size=2)
        assert len(page2) == 1
        assert page2[0].id == games[2].id

        page3 = get_fdroid_games(page=3, page_size=2)
        assert len(page3) == 0
