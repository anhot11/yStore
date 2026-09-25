import time
from unittest.mock import MagicMock, patch
import pytest

from app.itchio import (
    RateLimiter,
    build_itchio_url,
    is_url_allowed_by_robots,
    parse_itchio_html,
    sanitize_tag,
    scrape_itchio_games,
)


def test_parse_itchio_games_fixture(itchio_games_html):
    games = parse_itchio_html(itchio_games_html)
    assert len(games) > 0

    first = games[0]
    assert first.source == "itchio"
    assert first.id != ""
    assert first.title != ""
    assert first.developer != ""
    assert first.icon_url is not None
    assert first.icon_url.startswith("/cache/")
    # downloads must be None due to robots.txt compliance
    assert first.download_url is None
    assert isinstance(first.tags, list)
    assert len(first.tags) > 0


def test_parse_itchio_tag_fixture(itchio_tag_action_html):
    games = parse_itchio_html(itchio_tag_action_html)
    assert len(games) > 0
    for g in games:
        assert g.source == "itchio"
        assert g.title != ""


def test_parse_itchio_malformed_resilience(itchio_malformed_html, caplog):
    # Should not crash even with broken HTML
    games = parse_itchio_html(itchio_malformed_html)

    # 1 partially valid item survived
    assert len(games) == 1
    assert games[0].title == "Partially Valid Game"
    assert games[0].developer == "Corrupt Dev"
    assert games[0].tags == ["Simulation"]

    # Verify warning was logged
    warning_logs = [rec.message for rec in caplog.records if rec.levelname == "WARNING"]
    assert any("title" in log.lower() for log in warning_logs)


def test_parse_itchio_empty_html():
    games = parse_itchio_html("")
    assert games == []

    games_empty_div = parse_itchio_html("<div>No games here</div>")
    assert games_empty_div == []


def test_build_itchio_url():
    assert build_itchio_url() == "https://itch.io/games?page=1"
    assert build_itchio_url(page=3) == "https://itch.io/games?page=3"
    assert build_itchio_url(tag="Action", page=2) == "https://itch.io/games/tag-action?page=2"
    assert build_itchio_url(tag="Pixel Art") == "https://itch.io/games/tag-pixel-art?page=1"


def test_robots_txt_disallowed_paths():
    assert is_url_allowed_by_robots("/games") is True
    assert is_url_allowed_by_robots("/games/tag-android") is True
    assert is_url_allowed_by_robots("/search") is False
    assert is_url_allowed_by_robots("/game/download/12345") is False
    assert is_url_allowed_by_robots("/bundle/download/6789") is False
    assert is_url_allowed_by_robots("/checkout/pay") is False


def test_build_itchio_url_avoids_robots_disallowed():
    # If a tag attempts to navigate into /search
    url = build_itchio_url(tag="search")
    assert "/search" not in url
    assert "/games?page=1" in url


def test_sanitize_tag():
    assert sanitize_tag("2D Platformer") == "2d-platformer"
    assert sanitize_tag("Sci-Fi & Cyberpunk!!") == "sci-fi-cyberpunk"


def test_rate_limiter_timing():
    limiter = RateLimiter(min_interval_seconds=0.1)
    start = time.time()
    limiter.acquire()
    limiter.acquire()
    elapsed = time.time() - start
    assert elapsed >= 0.09


def test_scrape_itchio_games_mock(itchio_games_html):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = itchio_games_html

    with patch("requests.get", return_value=mock_resp):
        games = scrape_itchio_games(page=1)
        assert len(games) > 0
        assert games[0].source == "itchio"


def test_scrape_itchio_games_network_error():
    with patch("requests.get", side_effect=Exception("Connection refused")):
        games = scrape_itchio_games(page=1)
        assert games == []
