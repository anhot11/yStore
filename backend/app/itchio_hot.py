import logging
import re
from typing import Callable, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

from app.cache import cache_image
from app.config import (
    HTTP_TIMEOUT,
    ITCHIO_BASE_URL,
    ITCHIO_RATE_LIMIT_SECONDS,
    USER_AGENT,
)
from app.itchio import (
    RateLimiter,
    is_url_allowed_by_robots,
    itchio_rate_limiter,
    parse_itchio_cell,
    sanitize_tag,
)
from app.models import GameItem

logger = logging.getLogger(__name__)

# Regex pattern to match filename ending in .apk
APK_FILENAME_REGEX = re.compile(r"\b[\w\-_\.]+\.apk\b", re.IGNORECASE)


def build_itchio_hot_url(tag: Optional[str] = None, page: int = 1) -> str:
    """
    Build itch.io 'new-and-popular' (hot) section URL.
    Respects robots.txt policy.
    """
    page_num = max(1, page)
    if tag and tag.strip():
        slug = sanitize_tag(tag)
        if not is_url_allowed_by_robots(slug) or not is_url_allowed_by_robots(f"/games/tag-{slug}"):
            logger.warning(f"Tag '{tag}' violates robots.txt; defaulting to general hot games")
            return f"{ITCHIO_BASE_URL}/games/new-and-popular?page={page_num}"
        return f"{ITCHIO_BASE_URL}/games/tag-{slug}/new-and-popular?page={page_num}"

    return f"{ITCHIO_BASE_URL}/games/new-and-popular?page={page_num}"


def verify_game_has_apk(game_page_html: str) -> Tuple[bool, Optional[str]]:
    """
    Inspect individual itch.io game page HTML.
    Returns (True, filename) if at least one download file ends with '.apk'.
    Returns (False, None) otherwise.
    """
    if not game_page_html or not game_page_html.strip():
        return False, None

    soup = BeautifulSoup(game_page_html, "html.parser")

    # Target download sections: .upload, .upload_list_widget, .download_row, .upload_info
    download_sections = soup.select(
        ".upload, .upload_list_widget, .download_row, .upload_name, .file_format, "
        ".upload_info, a[href*='download'], .game_download, .formatted_description"
    )

    # 1. Search inside specific download widget elements
    for sec in download_sections:
        text = sec.get_text(separator=" ", strip=True)
        match = APK_FILENAME_REGEX.search(text)
        if match:
            return True, match.group(0)

    # 2. Broader search on whole body for any explicit .apk file listing
    body = soup.find("body")
    if body:
        match = APK_FILENAME_REGEX.search(body.get_text(separator=" ", strip=True))
        if match:
            return True, match.group(0)

    return False, None


def parse_and_verify_hot_games_offline(
    hot_listing_html: str,
    game_html_provider: Callable[[str], str],
    base_url: Optional[str] = None,
) -> List[GameItem]:
    """
    Parse a hot section listing HTML and verify each game with a provided
    game page HTML resolver (used for offline tests).
    """
    soup = BeautifulSoup(hot_listing_html, "html.parser")
    cells = soup.select(".game_cell")
    verified_games: List[GameItem] = []

    for cell in cells:
        item = parse_itchio_cell(cell, base_url=base_url)
        if not item:
            continue

        # Extract game page URL
        title_a = (
            cell.select_one(".game_title a")
            or cell.select_one("a.title")
            or cell.select_one("a.game_link")
        )
        game_url = title_a.get("href") if title_a else None

        if not game_url:
            continue

        try:
            game_html = game_html_provider(game_url)
            has_apk, apk_name = verify_game_has_apk(game_html)

            if has_apk:
                logger.info(f"Verified Android game with APK ({apk_name}): {item.title}")
                if "Android" not in item.tags:
                    item.tags.append("Android")
                if "Hot" not in item.tags:
                    item.tags.append("Hot")
                verified_games.append(item)
            else:
                logger.info(f"Discarding non-APK game: {item.title} ({game_url})")

        except Exception as e:
            logger.warning(f"Failed to verify game page {game_url}: {e}")

    return verified_games


def scrape_itchio_hot_games(
    tag: Optional[str] = None,
    page: int = 1,
    base_url: Optional[str] = None,
    rate_limiter: Optional[RateLimiter] = None,
) -> List[GameItem]:
    """
    Scrape itch.io 'new-and-popular' section and strictly verify that each candidate
    game offers an actual .apk download on its individual game page.
    """
    url = build_itchio_hot_url(tag=tag, page=page)
    logger.info(f"Scraping itch.io hot section from: {url}")

    limiter = rate_limiter or itchio_rate_limiter
    limiter.acquire()

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()

        # HTML provider fetching each candidate game's page with rate-limiting
        def fetch_game_page(game_url: str) -> str:
            limiter.acquire()
            logger.info(f"Visiting candidate game page to check for .apk: {game_url}")
            r = requests.get(game_url, headers=headers, timeout=HTTP_TIMEOUT)
            if r.status_code == 200:
                return r.text
            return ""

        return parse_and_verify_hot_games_offline(
            hot_listing_html=resp.text,
            game_html_provider=fetch_game_page,
            base_url=base_url,
        )

    except Exception as e:
        logger.error(f"Error scraping itch.io hot section ({url}): {e}", exc_info=True)
        return []
