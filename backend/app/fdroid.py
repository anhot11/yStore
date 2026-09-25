import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from app.cache import cache_image
from app.config import (
    CACHE_DIR,
    FDROID_CACHE_TTL_SECONDS,
    FDROID_INDEX_URL,
    FDROID_REPO_URL,
    HTTP_TIMEOUT,
    USER_AGENT,
)
from app.models import GameItem

logger = logging.getLogger(__name__)

FDROID_GAMES_CACHE_FILE = CACHE_DIR / "fdroid_games_cache.json"

# In-memory cached games list and timestamp
_in_memory_games: List[Dict[str, Any]] = []
_last_fetch_time: float = 0.0


def _extract_localized_text(field_data: Any) -> str:
    """Extract English or first available translation from an F-Droid localized field."""
    if isinstance(field_data, str):
        return field_data
    if isinstance(field_data, dict):
        if "en-US" in field_data:
            return field_data["en-US"]
        if "en" in field_data:
            return field_data["en"]
        if "en-GB" in field_data:
            return field_data["en-GB"]
        # Return first non-empty string value
        for val in field_data.values():
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def _strip_html(text: str) -> str:
    """Clean HTML tags from descriptions."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def parse_fdroid_package(
    pkg_id: str,
    pkg_data: Dict[str, Any],
    repo_address: str = FDROID_REPO_URL,
    base_url: Optional[str] = None,
) -> Optional[GameItem]:
    """Parse a single F-Droid package entry into a GameItem if it is a game."""
    metadata = pkg_data.get("metadata", {})
    categories = metadata.get("categories", [])

    # Filter for category "Games" / "* Game" (case-insensitive)
    is_game = any("game" in c.strip().lower() or c.strip().lower() == "games" for c in categories)
    if not is_game:
        return None

    # Title
    name_field = metadata.get("name")
    title = _extract_localized_text(name_field) or pkg_id

    # Description (prefer summary, or fallback to description)
    summary = _extract_localized_text(metadata.get("summary"))
    description = _extract_localized_text(metadata.get("description"))
    full_description = summary or description
    full_description = _strip_html(full_description)

    # Developer / Author
    developer = metadata.get("authorName") or metadata.get("authorEmail") or ""

    # Icon
    icon_url: Optional[str] = None
    icon_field = metadata.get("icon")
    if isinstance(icon_field, dict):
        # Localized map: {"en-US": {"name": "/pkg/icon.png"}} or {"name": "..."}
        icon_obj = icon_field.get("en-US") or icon_field.get("en") or next(iter(icon_field.values()), None)
        if isinstance(icon_obj, dict) and "name" in icon_obj:
            icon_path = icon_obj["name"]
            remote_icon = f"{repo_address.rstrip('/')}{icon_path}"
            icon_url = cache_image(remote_icon, base_url=base_url)
        elif isinstance(icon_obj, str):
            remote_icon = f"{repo_address.rstrip('/')}{icon_obj}"
            icon_url = cache_image(remote_icon, base_url=base_url)
    elif isinstance(icon_field, str):
        remote_icon = f"{repo_address.rstrip('/')}{icon_field}"
        icon_url = cache_image(remote_icon, base_url=base_url)

    # Screenshots
    screenshots: List[str] = []
    screenshots_field = metadata.get("screenshots", {})
    if isinstance(screenshots_field, dict):
        for device, loc_map in screenshots_field.items():
            if isinstance(loc_map, dict):
                shots = loc_map.get("en-US") or loc_map.get("en") or next(iter(loc_map.values()), [])
                if isinstance(shots, list):
                    for shot in shots:
                        if isinstance(shot, dict) and "name" in shot:
                            remote_shot = f"{repo_address.rstrip('/')}{shot['name']}"
                            cached_shot = cache_image(remote_shot, base_url=base_url)
                            if cached_shot:
                                screenshots.append(cached_shot)

    # Download URL (latest version APK)
    download_url: Optional[str] = None
    versions = pkg_data.get("versions", {})
    if isinstance(versions, dict) and versions:
        # Sort versions by added timestamp descending if possible
        sorted_versions = sorted(
            versions.values(),
            key=lambda v: v.get("added", 0),
            reverse=True,
        )
        for ver in sorted_versions:
            file_info = ver.get("file", {})
            apk_name = file_info.get("name")
            if apk_name:
                download_url = f"{repo_address.rstrip('/')}{apk_name}"
                break

    # Tags
    tags = [c for c in categories if c.strip()]

    return GameItem(
        id=pkg_id,
        title=title,
        source="fdroid",
        icon_url=icon_url,
        screenshots=screenshots,
        description=full_description,
        developer=developer,
        download_url=download_url,
        tags=tags,
    )


def parse_fdroid_index(
    index_data: Dict[str, Any],
    base_url: Optional[str] = None,
) -> List[GameItem]:
    """Parse an F-Droid index JSON object and return list of GameItems."""
    repo = index_data.get("repo", {})
    repo_address = repo.get("address", FDROID_REPO_URL)
    packages = index_data.get("packages", {})

    games: List[GameItem] = []
    for pkg_id, pkg_data in packages.items():
        try:
            item = parse_fdroid_package(pkg_id, pkg_data, repo_address=repo_address, base_url=base_url)
            if item is not None:
                games.append(item)
        except Exception as e:
            logger.warning(f"Error parsing F-Droid package {pkg_id}: {e}")

    return games


def load_cached_fdroid_games() -> Optional[List[Dict[str, Any]]]:
    """Load games from the local cache file if fresh."""
    global _in_memory_games, _last_fetch_time

    now = time.time()
    if _in_memory_games and (now - _last_fetch_time) < FDROID_CACHE_TTL_SECONDS:
        return _in_memory_games

    if FDROID_GAMES_CACHE_FILE.exists():
        try:
            mtime = FDROID_GAMES_CACHE_FILE.stat().st_mtime
            if (now - mtime) < FDROID_CACHE_TTL_SECONDS:
                with open(FDROID_GAMES_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    _in_memory_games = data
                    _last_fetch_time = mtime
                    return data
        except Exception as e:
            logger.warning(f"Failed to read F-Droid games cache file: {e}")

    return None


def save_cached_fdroid_games(games: List[GameItem]) -> None:
    """Save parsed games to local cache file."""
    global _in_memory_games, _last_fetch_time
    try:
        raw_list = [g.model_dump() for g in games]
        temp_file = FDROID_GAMES_CACHE_FILE.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(raw_list, f, indent=2)
        temp_file.replace(FDROID_GAMES_CACHE_FILE)
        _in_memory_games = raw_list
        _last_fetch_time = time.time()
    except Exception as e:
        logger.warning(f"Failed to save F-Droid games cache: {e}")


def fetch_and_update_fdroid_games(base_url: Optional[str] = None) -> List[GameItem]:
    """Fetch index-v2.json from F-Droid, parse games, and update cache."""
    logger.info(f"Fetching F-Droid index from {FDROID_INDEX_URL}...")
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(FDROID_INDEX_URL, headers=headers, timeout=HTTP_TIMEOUT * 2)
    resp.raise_for_status()

    index_data = resp.json()
    games = parse_fdroid_index(index_data, base_url=base_url)
    save_cached_fdroid_games(games)
    logger.info(f"Successfully loaded and cached {len(games)} games from F-Droid")
    return games


def get_fdroid_games(
    tag: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    base_url: Optional[str] = None,
    force_refresh: bool = False,
) -> List[GameItem]:
    """
    Get games from F-Droid with optional tag filtering and pagination.
    Uses cached index data if available.
    """
    cached_raw = None if force_refresh else load_cached_fdroid_games()

    if cached_raw is not None:
        games = [GameItem(**item) for item in cached_raw]
    else:
        try:
            games = fetch_and_update_fdroid_games(base_url=base_url)
        except Exception as e:
            logger.error(f"Failed to fetch live F-Droid index: {e}")
            if FDROID_GAMES_CACHE_FILE.exists():
                logger.info("Falling back to stale F-Droid cache file")
                with open(FDROID_GAMES_CACHE_FILE, "r", encoding="utf-8") as f:
                    games = [GameItem(**item) for item in json.load(f)]
            else:
                games = []

    # Tag filter
    if tag:
        tag_lower = tag.strip().lower()
        games = [
            g for g in games
            if any(tag_lower in t.lower() for t in g.tags)
        ]

    # Pagination (page is 1-indexed)
    page = max(1, page)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    return games[start_idx:end_idx]
