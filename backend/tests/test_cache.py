import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from app.cache import (
    CACHE_DIR,
    cache_image,
    get_cached_image_path,
    get_filename_for_url,
    register_image_url,
)


def test_filename_deterministic():
    url = "https://img.itch.zone/test12345/315x250/image.png"
    name1 = get_filename_for_url(url)
    name2 = get_filename_for_url(url)
    assert name1 == name2
    assert name1.endswith(".png")


def test_cache_image_url_mapping():
    url = "https://img.itch.zone/screenshot/1.jpg"
    cached_url = cache_image(url)
    assert cached_url.startswith("/cache/")
    assert cached_url.endswith(".jpg")


def test_cache_image_with_base_url():
    url = "https://f-droid.org/repo/icons/game.png"
    cached_url = cache_image(url, base_url="http://10.0.2.2:8000")
    assert cached_url.startswith("http://10.0.2.2:8000/cache/")
    assert cached_url.endswith(".png")


def test_cache_image_none_returns_none():
    assert cache_image(None) is None
    assert cache_image("") is None


def test_get_cached_image_path_existing(tmp_path, monkeypatch):
    test_file = tmp_path / "existing.png"
    test_file.write_bytes(b"PNG_SAMPLE_DATA")

    with patch("app.cache.CACHE_DIR", tmp_path):
        res = get_cached_image_path("existing.png")
        assert res == test_file
        assert res.read_bytes() == b"PNG_SAMPLE_DATA"


def test_get_cached_image_path_download_mock(tmp_path):
    remote_url = "https://example.com/assets/banner.png"
    filename = register_image_url(remote_url)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.iter_content.return_value = [b"MOCK_IMAGE_DATA"]

    with patch("app.cache.CACHE_DIR", tmp_path):
        with patch("requests.get", return_value=mock_resp) as mock_get:
            path = get_cached_image_path(filename)
            assert path is not None
            assert path.exists()
            assert path.read_bytes() == b"MOCK_IMAGE_DATA"
            mock_get.assert_called_once()


def test_get_cached_image_path_nonexistent_returns_none(tmp_path):
    with patch("app.cache.CACHE_DIR", tmp_path):
        assert get_cached_image_path("non_existent_file.png") is None
