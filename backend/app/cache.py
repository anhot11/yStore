import hashlib
import json
import logging
import mimetypes
import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse

import requests
from app.config import CACHE_DIR, USER_AGENT, HTTP_TIMEOUT

logger = logging.getLogger(__name__)

REGISTRY_FILE = CACHE_DIR / "registry.json"
_url_to_filename: Dict[str, str] = {}
_filename_to_url: Dict[str, str] = {}


def _load_registry() -> None:
    global _url_to_filename, _filename_to_url
    if REGISTRY_FILE.exists():
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                _filename_to_url = json.load(f)
                _url_to_filename = {v: k for k, v in _filename_to_url.items()}
        except Exception as e:
            logger.warning(f"Failed to load image cache registry: {e}")
            _filename_to_url = {}
            _url_to_filename = {}


def _save_registry() -> None:
    try:
        temp_file = REGISTRY_FILE.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(_filename_to_url, f, indent=2)
        temp_file.replace(REGISTRY_FILE)
    except Exception as e:
        logger.warning(f"Failed to save image cache registry: {e}")


# Initialize registry on import
_load_registry()


def get_filename_for_url(remote_url: str) -> str:
    """Generate a deterministic, safe filename for a remote image URL."""
    if remote_url in _url_to_filename:
        return _url_to_filename[remote_url]

    url_hash = hashlib.sha256(remote_url.encode("utf-8")).hexdigest()[:24]

    # Extract extension from path
    parsed = urlparse(remote_url)
    ext = os.path.splitext(parsed.path)[1].lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"]:
        # default to .jpg or .png
        ext = ".png" if ".png" in remote_url.lower() else ".jpg"

    filename = f"{url_hash}{ext}"
    _url_to_filename[remote_url] = filename
    _filename_to_url[filename] = remote_url
    _save_registry()
    return filename


def register_image_url(remote_url: str) -> str:
    """Register a remote URL and return the local filename."""
    if not remote_url:
        return ""
    return get_filename_for_url(remote_url)


def get_cached_image_path(filename: str) -> Optional[Path]:
    """
    Retrieve local cached image path. If not downloaded yet, fetch from the
    registered remote URL and save to cache.
    """
    # Sanitize filename
    safe_name = os.path.basename(filename)
    if not safe_name or safe_name != filename:
        return None

    target_path = CACHE_DIR / safe_name
    if target_path.exists() and target_path.stat().st_size > 0:
        return target_path

    # Check if we have remote URL to download
    remote_url = _filename_to_url.get(safe_name)
    if not remote_url:
        logger.warning(f"No remote URL registered for cache file: {safe_name}")
        return None

    # Fetch and cache
    try:
        logger.info(f"Downloading image to cache: {remote_url} -> {safe_name}")
        headers = {"User-Agent": USER_AGENT}
        resp = requests.get(remote_url, headers=headers, timeout=HTTP_TIMEOUT, stream=True)
        if resp.status_code == 200:
            temp_path = target_path.with_suffix(".downloading")
            with open(temp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            temp_path.replace(target_path)
            return target_path
        else:
            logger.warning(f"Failed to download image {remote_url}, status: {resp.status_code}")
            return None
    except Exception as e:
        logger.warning(f"Error downloading image {remote_url} to cache: {e}")
        return None


def cache_image(
    remote_url: Optional[str],
    eager: bool = False,
    base_url: Optional[str] = None
) -> Optional[str]:
    """
    Converts a remote image URL to an internal cached endpoint URL (/cache/<filename>).
    If eager is True, attempts to download immediately.
    """
    if not remote_url:
        return None

    # If already a cached URL, return as-is
    if remote_url.startswith("/cache/"):
        return remote_url

    filename = register_image_url(remote_url)
    if eager:
        get_cached_image_path(filename)

    prefix = base_url.rstrip("/") if base_url else ""
    return f"{prefix}/cache/{filename}"
