# yStore Game Catalog Aggregator Backend

FastAPI-based game catalog aggregator and external developer publishing platform designed for the **yStore** Android client.

---

## Key Features

### 1. Catalog Aggregation (F-Droid & itch.io)
- **Zero Browser Automation**: Built purely with `requests` + `BeautifulSoup` for HTML parsing and direct HTTP JSON calls. No Selenium / Playwright.
- **F-Droid Integration**: Consumes official `index-v2.json`, filters by game categories (e.g. `Games`, `Action Game`, `Puzzle Game`, `Board Game`), maps to unified schema, and provides instant responses via local TTL caching.
- **itch.io Public Scraper**:
  - Scrapes public browse pages (`https://itch.io/games` and `https://itch.io/games/tag-<tag>`).
  - **robots.txt compliant**: Blocks `/search`, `/game/download/*`, `/embed/*`, `/checkout/*`.
  - **Rate Limiting**: Thread-safe rate limiter (1.5s delay between outbound calls).
  - **Identifiable User-Agent**: Configured as `yStore-Aggregator/1.0 (+https://github.com/anhot11/yStore)`.
- **itch.io "Hot" Section & Android-Only Verification**:
  - Scrapes the `new-and-popular` section (`https://itch.io/games/new-and-popular`).
  - **Strict APK Verification**: Does **NOT** rely on platform tags/icons on the grid listing. Visits the individual public game page and verifies that at least one download file ends with `.apk`. Games without verified `.apk` files are discarded.
- **Local Image Cache**: Images are cached locally in `/cache` and served from `GET /cache/{filename}` to avoid hotlinking or external origin tracking.

### 2. External Developer Publishing Flow
- **GitHub App Authentication**:
  - Implements GitHub App OAuth flow (`/auth/github/login`, `/auth/github/callback`) and installation token generation via RS256 JWT.
  - Permissions: `contents:write` and `administration:write`.
- **Publisher Onboarding ("Crear Compañía/Publisher")**:
  - Endpoint `POST /publisher/create-repo` creates a repository in the developer's account from a Fastlane-style template (identical to F-Droid's Triple-T format):
    ```text
    /metadata/android/en-US/title.txt
    /metadata/android/en-US/short_description.txt
    /metadata/android/en-US/full_description.txt
    /metadata/android/en-US/images/icon.png
    /metadata/android/en-US/images/phoneScreenshots/*.png
    /metadata/android/en-US/changelogs/<versionCode>.txt
    ```
  - The APK is published as a GitHub Release asset, not committed to the repository.
- **Webhook Synchronization (No Polling)**:
  - Registers a repository webhook on repo creation listening for `release published` events.
  - Endpoint `POST /webhooks/github` validates GitHub HMAC-SHA256 signature (`X-Hub-Signature-256`).
  - Downloads the release APK asset, reads Fastlane metadata files, and validates schema integrity.
- **Modular Security Scanning**:
  - Generic interface (`SecurityScanner`) allows interchangeable scan engines.
  - **VirusTotal Scanner (`VirusTotalScanner`)**:
    1. First does a hash lookup via `GET /files/{hash}`.
    2. If not found (404), uploads the APK (`POST /files`) and polls the report (`GET /analyses/{id}`).
    3. Respects VirusTotal free-tier rate limits (4 requests/minute, 15s interval).
    4. Enforces detection threshold: blocks if malicious detections > 2 (status: `rejected`), otherwise `approved`.
  - **ClamAV Scanner (`ClamAVScanner`)**: High-throughput local scanner for instant first-tier checks.
  - **Composite Scanner (`CompositeScanner`)**: Chains ClamAV first, short-circuiting on virus detection before consuming VirusTotal quota.
  - Stores scan results alongside the listing with review status (`pending`, `approved`, `rejected`).
  - Approved community listings are automatically included in `GET /catalog`.

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

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/catalog` | Unified catalog (`source`: `fdroid`, `itchio`, `community`, `all`; `section`: `hot`, `all`; `tag`, `page`) |
| `GET` | `/catalog/hot` | Itch.io `new-and-popular` games with strict `.apk` verification |
| `GET` | `/cache/{filename}` | Serve cached images with immutable HTTP cache headers |
| `GET` | `/auth/github/login` | Initiate GitHub App OAuth login |
| `GET` | `/auth/github/callback` | OAuth callback to exchange authorization code for access token |
| `POST` | `/publisher/create-repo` | Create Fastlane-structured repository and register webhook |
| `GET` | `/publisher/listings` | List developer game submissions and their scan status |
| `POST` | `/webhooks/github` | Webhook receiver for GitHub release events and auto-scanning |
| `GET` | `/health` | Health check endpoint |

---

## Installation & Running

```bash
cd /root/app/yStore/backend

# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Running Offline Unit Tests

```bash
pytest tests/ -v
```

The test suite runs **63 unit tests** 100% offline using local fixtures:
- `test_models.py`: Schema validation.
- `test_cache.py`: Deterministic hashing, URL mapping, mock image download.
- `test_fdroid.py`: Index parsing, category filtering, version selection.
- `test_itchio.py`: Standard scrape parsing, robots.txt, malformed HTML resilience.
- `test_itchio_hot.py`: `new-and-popular` scraping and individual page `.apk` download verification.
- `test_github_app.py`: RS256 JWT generation, OAuth code exchange, Fastlane template repo creation.
- `test_scanner.py`: VirusTotal hash lookup, 404 upload & polling, threshold blocking, ClamAV & Composite scanner.
- `test_webhook.py`: HMAC-SHA256 signature verification, metadata validation, release APK processing.
- `test_publisher_db.py`: SQLite persistence and listing review status management.
- `test_api.py`: FastAPI endpoints integration tests via TestClient.
