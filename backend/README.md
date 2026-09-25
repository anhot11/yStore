# yStore Game Catalog Aggregator Backend

FastAPI-based game catalog aggregator designed for the **yStore** Android client.

## Features
- **No Browser Automation**: Exclusively uses `requests` and `BeautifulSoup` for HTML parsing, and direct HTTP calls for structured JSON APIs. Zero Playwright / Selenium dependencies.
- **F-Droid Integration**: Consumes official `index-v2.json`, filters by game categories (e.g. Games, Action Game, Puzzle Game, etc.), maps to unified schema, and provides instant responses via local TTL caching.
- **itch.io Scraper**:
  - Scrapes public browse pages (`https://itch.io/games`, `https://itch.io/games/tag-<tag>`).
  - **robots.txt compliant**: Strictly blocks disallowed paths (`/search`, `/game/download/*`, `/embed/*`, `/checkout/*`).
  - **Rate Limiting**: Built-in thread-safe rate limiter (minimum 1.5s delay between outbound calls).
  - **Identifiable User-Agent**: Configurable User-Agent identifying the client (`yStore-Aggregator/1.0 (+https://github.com/anhot11/yStore)`).
  - **Resilient Parsing**: Catches missing or modified HTML tags with descriptive warnings, preventing server crashes.
- **Local Image Cache**: Remote images (icons, thumbnails, screenshots) are stored in `/cache` and served directly through `GET /cache/{filename}` to avoid hotlinking or leaking client requests to external origins.
- **Offline Unit Testing**: 100% offline test suite using local HTML/JSON fixtures. Zero live scraping during tests.

---

## Unified JSON Output Schema

```json
{
  "id": "app.crossword.yourealwaysbe.forkyz",
  "title": "Forkyz",
  "source": "fdroid",
  "icon_url": "/cache/5166411afbf505fe0dd902f1.png",
  "screenshots": [],
  "description": "Crosswords puzzle game for Android.",
  "developer": "Forkyz Dev",
  "download_url": "https://f-droid.org/repo/app.crossword.yourealwaysbe.forkyz_8600000.apk",
  "tags": ["Word Game"]
}
```

---

## API Endpoints

### 1. `GET /catalog`
Query Parameters:
- `source`: `"fdroid"`, `"itchio"`, or `"all"` (default: `"all"`).
- `tag`: Optional category or tag name (e.g., `"Action"`, `"Puzzle"`, `"Board"`).
- `page`: Page number (1-indexed, default: `1`).

Examples:
- `GET /catalog?source=fdroid&page=1`
- `GET /catalog?source=itchio&tag=pixel-art&page=2`
- `GET /catalog?tag=Action`

### 2. `GET /cache/{filename}`
Serves cached images locally with aggressive HTTP caching (`Cache-Control: public, max-age=604800, immutable`). Downloads remote assets on-demand upon first access and caches them permanently on disk.

### 3. `GET /health`
Returns `{"status": "ok"}` for service health monitoring.

---

## Installation & Running

### Requirements
- Python 3.10+
- Dependencies in `requirements.txt`:
  ```bash
  pip install -r requirements.txt
  ```

### Start the Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Running Offline Unit Tests

```bash
pytest tests/ -v
```

All 35 unit tests run against local fixtures in `tests/fixtures/`:
- `tests/fixtures/fdroid_sample.json`
- `tests/fixtures/itchio_games.html`
- `tests/fixtures/itchio_tag_action.html`
- `tests/fixtures/itchio_malformed.html`
