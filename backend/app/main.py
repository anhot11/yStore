import json
import logging
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import unquote

from fastapi import Body, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from app.cache import get_cached_image_path
from app.config import (
    BACKEND_PUBLIC_URL,
    GITHUB_CLIENT_ID,
    GITHUB_WEBHOOK_SECRET,
)
from app.fdroid import get_fdroid_games
from app.github_app import (
    create_publisher_repo,
    exchange_oauth_code,
    get_github_user,
)
from app.itchio import scrape_itchio_games
from app.itchio_hot import scrape_itchio_hot_games
from app.models import GameItem
from app.publisher_db import (
    get_approved_game_items,
    get_listing,
    list_listings,
)
from app.scanner.base import ReviewStatus
from app.webhook import process_release_webhook, verify_github_signature

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ystore-backend")

app = FastAPI(
    title="yStore Game Catalog Aggregator",
    description="Backend API aggregating game catalogs from F-Droid, itch.io, and verified community developers.",
    version="2.0.0",
)

# Enable CORS for all clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateRepoRequest(BaseModel):
    token: str
    repo_name: str
    title: str = "My Awesome Game"
    short_desc: str = "A fast-paced Android game."
    full_desc: str = "Full description of features, controls, and gameplay."
    installation_id: Optional[str] = None


@app.get("/")
def root():
    return {
        "service": "yStore Game Catalog Aggregator",
        "version": "2.0.0",
        "endpoints": {
            "catalog": "/catalog?source={fdroid|itchio|community|all}&section={hot|all}&tag={tag}&page={page}",
            "catalog_hot": "/catalog/hot?tag={tag}&page={page}",
            "cache": "/cache/{filename}",
            "auth_github_login": "/auth/github/login",
            "auth_github_callback": "/auth/github/callback",
            "publisher_create_repo": "/publisher/create-repo",
            "publisher_listings": "/publisher/listings",
            "webhooks_github": "/webhooks/github",
        },
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# 1. GitHub App Authentication & Publisher Onboarding
# ---------------------------------------------------------------------------

@app.get("/auth/github/login")
def github_app_login():
    """Redirect developer to GitHub App OAuth login with required permissions."""
    if not GITHUB_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GITHUB_CLIENT_ID not configured")

    # Scopes: repo, write:repo_hook, admin:repo_hook (contents:write, administration:write)
    scope = "repo,write:repo_hook,admin:repo_hook"
    auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&scope={scope}"
        f"&redirect_uri={BACKEND_PUBLIC_URL.rstrip('/')}/auth/github/callback"
    )
    return RedirectResponse(url=auth_url)


@app.get("/auth/github/callback")
def github_app_callback(code: str = Query(..., description="Authorization code from GitHub")):
    """Exchange authorization code for user access token and return profile."""
    try:
        token_data = exchange_oauth_code(code)
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=400,
                detail=f"GitHub authentication failed: {token_data.get('error_description', 'No access token')}",
            )

        user_info = get_github_user(access_token)
        return {
            "status": "authenticated",
            "user": user_info.get("login"),
            "name": user_info.get("name"),
            "token": access_token,
            "token_type": token_data.get("token_type"),
            "scope": token_data.get("scope"),
        }
    except Exception as e:
        logger.error(f"GitHub OAuth callback error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/publisher/create-repo")
def publisher_create_repo_endpoint(req: CreateRepoRequest):
    """
    Publisher Onboarding Flow:
    Creates a Fastlane-structured repository in the developer's account,
    sets up /metadata/android/en-US/* structure, and registers release webhook.
    """
    try:
        result = create_publisher_repo(
            token=req.token,
            repo_name=req.repo_name,
            title=req.title,
            short_desc=req.short_desc,
            full_desc=req.full_desc,
            installation_id=req.installation_id,
        )
        return {
            "status": "created",
            "message": "Publisher repository successfully created and initialized with Fastlane template.",
            "data": result,
        }
    except Exception as e:
        logger.error(f"Error creating publisher repository: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/publisher/listings")
def get_publisher_listings_endpoint(
    status: Optional[str] = Query(None, description="Filter by status: pending, approved, rejected"),
    publisher: Optional[str] = Query(None, description="Filter by publisher username"),
):
    """List submitted game listings and their security scan review status."""
    rev_status = None
    if status:
        try:
            rev_status = ReviewStatus(status.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status. Must be pending, approved, or rejected.")

    listings = list_listings(status=rev_status, publisher_id=publisher)
    return listings


# ---------------------------------------------------------------------------
# 2. Webhook Receiver (Sync via Webhook, Security Scanning, Review)
# ---------------------------------------------------------------------------

@app.post("/webhooks/github")
async def github_webhook_endpoint(
    request: Request,
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
):
    """
    GitHub Webhook receiver.
    Verifies HMAC-SHA256 signature, parses 'release' published events,
    downloads the APK, validates Fastlane metadata, runs VirusTotal security scan,
    and updates catalog listing status.
    """
    raw_body = await request.body()

    # 1. Verify HMAC-SHA256 signature
    if not verify_github_signature(raw_body, x_hub_signature_256, GITHUB_WEBHOOK_SECRET):
        logger.warning("Rejected webhook request: invalid or missing HMAC-SHA256 signature")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # 2. Handle release event
    if x_github_event != "release":
        logger.info(f"Received non-release event: {x_github_event}; ignored")
        return {"status": "ignored", "event": x_github_event}

    try:
        payload = json.loads(raw_body.decode("utf-8"))
        result = process_release_webhook(payload)
        return {"status": "processed", "result": result}
    except Exception as e:
        logger.error(f"Error processing GitHub release webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 3. Catalog Endpoints (F-Droid, itch.io standard, itch.io hot Android-only, Community)
# ---------------------------------------------------------------------------

@app.get("/catalog", response_model=List[GameItem])
def get_catalog(
    request: Request,
    source: Optional[str] = Query(
        None,
        description="Catalog source: 'fdroid', 'itchio', 'community', or 'all' (default)",
    ),
    section: Optional[str] = Query(
        None,
        description="Section: 'hot' (new and popular, verified Android APKs only) or 'standard'",
    ),
    tag: Optional[str] = Query(
        None,
        description="Filter games by category or tag (e.g. 'Action', 'Puzzle')",
    ),
    page: int = Query(
        1,
        ge=1,
        description="Page number (1-indexed, default: 1)",
    ),
):
    """
    Unified catalog endpoint. Aggregates games from F-Droid, itch.io, and verified Community developers.
    If section='hot', strictly returns itch.io hot games that offer verified .apk downloads.
    """
    results: List[GameItem] = []
    clean_source = source.strip().lower() if source else "all"
    is_hot = (section or "").strip().lower() == "hot"

    # F-Droid
    if not is_hot and clean_source in ("fdroid", "all"):
        try:
            fdroid_games = get_fdroid_games(tag=tag, page=page, page_size=20)
            results.extend(fdroid_games)
        except Exception as e:
            logger.error(f"Error retrieving F-Droid catalog: {e}", exc_info=True)

    # itch.io (Hot Section vs Standard Browse)
    if clean_source in ("itchio", "all"):
        try:
            if is_hot:
                # Scrapes new-and-popular and strictly verifies .apk files on each game's page
                itchio_games = scrape_itchio_hot_games(tag=tag, page=page)
            else:
                itchio_games = scrape_itchio_games(tag=tag, page=page)
            results.extend(itchio_games)
        except Exception as e:
            logger.error(f"Error retrieving itch.io catalog: {e}", exc_info=True)

    # Community Verified Publishers (Approved listings from GitHub releases)
    if not is_hot and clean_source in ("community", "all"):
        try:
            community_games = get_approved_game_items()
            if tag:
                t_lower = tag.strip().lower()
                community_games = [g for g in community_games if any(t_lower in t.lower() for t in g.tags)]
            results.extend(community_games)
        except Exception as e:
            logger.error(f"Error retrieving community catalog: {e}", exc_info=True)

    return results


@app.get("/catalog/hot", response_model=List[GameItem])
def get_catalog_hot(
    tag: Optional[str] = Query(None, description="Optional tag filter"),
    page: int = Query(1, ge=1, description="Page number"),
):
    """Convenience endpoint dedicated to the itch.io 'new-and-popular' section with Android APK verification."""
    return scrape_itchio_hot_games(tag=tag, page=page)


# ---------------------------------------------------------------------------
# 4. Cache Endpoint
# ---------------------------------------------------------------------------

@app.get("/cache/{filename:path}")
def serve_cached_image(filename: str):
    """
    Serve locally cached image. Downloads from registered remote URL on-demand
    if not already cached locally.
    """
    clean_filename = unquote(filename).strip("/")
    image_path = get_cached_image_path(clean_filename)

    if not image_path or not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found in cache")

    ext = image_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path=str(image_path),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=604800, immutable"},
    )
