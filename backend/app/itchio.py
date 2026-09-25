import logging
import re
import threading
import time
from typing import List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag
from app.cache import cache_image
from app.config import (
    HTTP_TIMEOUT,
    ITCHIO_BASE_URL,
    ITCHIO_RATE_LIMIT_SECONDS,
    USER_AGENT,
)
from app.models import GameItem

logger = logging.getLogger(__name__)

# Paths disallowed by itch.io robots.txt
DISALLOWED_PATHS = [
    "/embed/",
    "/embed-upload/",
    "/search",
    "/checkout/",
    "/game/download/",
    "/bundle/download/",
    "/register-for-purchase/",
    "/email-feedback/",
]


class RateLimiter:
    """Thread-safe rate limiter to enforce delays between external HTTP requests."""

    def __init__(self, min_interval_seconds: float = ITCHIO_RATE_LIMIT_SECONDS):
        self.min_interval = min_interval_seconds
        self.last_request_time = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.time()
            elapsed = now - self.last_request_time
            if elapsed < self.min_interval:
                sleep_time = self.min_interval - elapsed
                logger.debug(f"Rate limiting active: sleeping for {sleep_time:.2f}s")
                time.sleep(sleep_time)
            self.last_request_time = time.time()


# Global rate limiter instance
itchio_rate_limiter = RateLimiter(ITCHIO_RATE_LIMIT_SECONDS)


def is_url_allowed_by_robots(url_or_path: str) -> bool:
    """Check if the given path or URL violates itch.io robots.txt rules."""
    path = url_or_path.lower()
    for disallowed in DISALLOWED_PATHS:
        if disallowed in path:
            return False
        clean = disallowed.strip("/")
        if path == clean or path.endswith(f"-{clean}") or f"/{clean}" in path or f"-{clean}-" in path:
            return False
    return True


def sanitize_tag(tag: str) -> str:
    """Sanitize tag string into a valid itch.io slug."""
    clean = tag.strip().lower()
    clean = re.sub(r"[^\w\-]", "-", clean)
    clean = re.sub(r"-+", "-", clean).strip("-")
    return clean


def build_itchio_url(tag: Optional[str] = None, page: int = 1) -> str:
    """Build public navigation URL for itch.io."""
    page_num = max(1, page)
    if tag and tag.strip():
        slug = sanitize_tag(tag)
        # Avoid disallowed paths like /search or /download
        if not is_url_allowed_by_robots(slug) or not is_url_allowed_by_robots(f"/games/tag-{slug}"):
            logger.warning(f"Requested tag '{tag}' violates robots.txt policy; defaulting to browse")
            return f"{ITCHIO_BASE_URL}/games?page={page_num}"
        return f"{ITCHIO_BASE_URL}/games/tag-{slug}?page={page_num}"

    return f"{ITCHIO_BASE_URL}/games?page={page_num}"


def parse_itchio_cell(cell: Tag, base_url: Optional[str] = None) -> Optional[GameItem]:
    """
    Parse a single .game_cell BeautifulSoup Tag into a GameItem.
    Catches errors defensively and logs clear warnings.
    """
    try:
        game_id = cell.get("data-game_id")

        # 1. Title and game URL
        title_tag = (
            cell.select_one(".game_title a")
            or cell.select_one("a.title")
            or cell.select_one(".title a")
            or cell.select_one("a.game_link")
            or cell.select_one(".game_title")
        )

        if not title_tag:
            logger.warning(f"Could not find title element in game_cell (id={game_id})")
            return None

        title = title_tag.get_text(strip=True)
        if not title:
            logger.warning(f"Empty title text in game_cell (id={game_id})")
            return None

        game_href = title_tag.get("href", "")
        if not game_id:
            # Fallback to slug from link or title
            game_id = game_href.rstrip("/").split("/")[-1] if game_href else sanitize_tag(title)

        # 2. Developer / Author
        author_tag = (
            cell.select_one(".game_author a")
            or cell.select_one(".user_link")
            or cell.select_one(".game_author")
        )
        developer = author_tag.get_text(strip=True) if author_tag else ""

        # 3. Description
        desc_tag = cell.select_one(".game_text") or cell.select_one(".game_short_text")
        description = ""
        if desc_tag:
            description = desc_tag.get("title") or desc_tag.get_text(strip=True)

        # 4. Thumbnail / Icon URL
        icon_url: Optional[str] = None
        img_tag = cell.select_one(".game_thumb img") or cell.select_one("img")
        if img_tag:
            remote_img = (
                img_tag.get("data-lazy_src")
                or img_tag.get("data-screenshot_custom")
                or img_tag.get("src")
            )
            if remote_img and remote_img.startswith("http"):
                icon_url = cache_image(remote_img, base_url=base_url)

        # 5. Screenshots
        screenshots: List[str] = []
        # Check for any secondary screenshots in data attributes
        if img_tag and img_tag.get("data-screenshot_custom"):
            custom_shot = img_tag.get("data-screenshot_custom")
            if custom_shot.startswith("http"):
                cached_shot = cache_image(custom_shot, base_url=base_url)
                if cached_shot and cached_shot != icon_url:
                    screenshots.append(cached_shot)

        # 6. Tags and Genres
        tags: List[str] = []
        genre_tag = cell.select_one(".game_genre")
        if genre_tag:
            genre = genre_tag.get_text(strip=True)
            if genre:
                tags.append(genre)

        # Platform indicators (Windows, Linux, macOS, Android, Web)
        for platform_elem in cell.select(".game_platform span"):
            plat_title = platform_elem.get("title") or platform_elem.get_text(strip=True)
            if plat_title:
                clean_plat = plat_title.replace("Download for ", "").strip()
                if clean_plat and clean_plat not in tags:
                    tags.append(clean_plat)
            else:
                classes = platform_elem.get("class", [])
                for cls in classes:
                    if "icon-android" in cls and "Android" not in tags:
                        tags.append("Android")
                    elif "icon-windows" in cls and "Windows" not in tags:
                        tags.append("Windows")
                    elif "icon-tux" in cls and "Linux" not in tags:
                        tags.append("Linux")
                    elif "icon-apple" in cls and "macOS" not in tags:
                        tags.append("macOS")

        # Additional tag labels
        for tag_elem in cell.select(".game_tag, .tag"):
            t_text = tag_elem.get_text(strip=True)
            if t_text and t_text not in tags:
                tags.append(t_text)

        # 7. Download URL
        # Respect robots.txt: do NOT touch /game/download/ or /search
        # itch.io downloads require token/session/disallowed paths, so download_url is None
        download_url: Optional[str] = None

        return GameItem(
            id=str(game_id),
            title=title,
            source="itchio",
            icon_url=icon_url,
            screenshots=screenshots,
            description=description,
            developer=developer,
            download_url=download_url,
            tags=tags,
        )

    except Exception as e:
        logger.warning(f"Error parsing itch.io game cell: {e}", exc_info=True)
        return None


def parse_itchio_html(html_content: str, base_url: Optional[str] = None) -> List[GameItem]:
    """
    Parse an itch.io HTML string into a list of GameItem objects.
    Resilient to structural changes with clear logging and zero crashes.
    """
    if not html_content or not html_content.strip():
        logger.warning("Empty HTML content received for itch.io parsing")
        return []

    soup = BeautifulSoup(html_content, "html.parser")
    cells = soup.select(".game_cell")

    if not cells:
        logger.warning(
            "No '.game_cell' elements found in itch.io HTML. "
            "Page might be empty or itch.io layout has changed."
        )
        return []

    games: List[GameItem] = []
    for cell in cells:
        item = parse_itchio_cell(cell, base_url=base_url)
        if item is not None:
            games.append(item)

    logger.info(f"Successfully parsed {len(games)}/{len(cells)} games from itch.io HTML")
    return games


def scrape_itchio_games(
    tag: Optional[str] = None,
    page: int = 1,
    base_url: Optional[str] = None,
    rate_limiter: Optional[RateLimiter] = None,
) -> List[GameItem]:
    """
    Scrape public navigation pages from itch.io.
    Enforces rate-limiting, custom User-Agent, and robots.txt compliance.
    """
    url = build_itchio_url(tag=tag, page=page)
    logger.info(f"Scraping itch.io public games from: {url}")

    # Enforce rate-limiting
    limiter = rate_limiter or itchio_rate_limiter
    limiter.acquire()

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    try:
        response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
        if response.status_code == 404:
            logger.warning(f"itch.io page not found (404): {url}")
            return []
        elif response.status_code == 429:
            logger.error("itch.io rate limit exceeded (HTTP 429)")
            return []
        response.raise_for_status()

        return parse_itchio_html(response.text, base_url=base_url)

    except requests.RequestException as e:
        logger.error(f"Network error while scraping itch.io ({url}): {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error while scraping itch.io ({url}): {e}", exc_info=True)
        return []
