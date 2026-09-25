import logging
from typing import List, Literal, Optional
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.cache import get_cached_image_path
from app.fdroid import get_fdroid_games
from app.itchio import scrape_itchio_games
from app.models import GameItem

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ystore-backend")

app = FastAPI(
    title="yStore Game Catalog Aggregator",
    description="Backend API aggregating game catalogs from F-Droid and itch.io for Android clients.",
    version="1.0.0",
)

# Enable CORS for all clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "service": "yStore Game Catalog Aggregator",
        "version": "1.0.0",
        "endpoints": {
            "catalog": "/catalog?source={fdroid|itchio|all}&tag={tag}&page={page}",
            "cache": "/cache/{filename}",
        },
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/catalog", response_model=List[GameItem])
def get_catalog(
    request: Request,
    source: Optional[str] = Query(
        None,
        description="Catalog source: 'fdroid', 'itchio', or 'all' (default)",
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
    Unified catalog endpoint aggregating games from F-Droid and itch.io.
    Returns normalized JSON conforming to the unified schema.
    """
    results: List[GameItem] = []
    clean_source = source.strip().lower() if source else "all"

    # F-Droid
    if clean_source in ("fdroid", "all"):
        try:
            fdroid_games = get_fdroid_games(tag=tag, page=page, page_size=20)
            results.extend(fdroid_games)
        except Exception as e:
            logger.error(f"Error retrieving F-Droid catalog: {e}", exc_info=True)

    # itch.io
    if clean_source in ("itchio", "all"):
        try:
            itchio_games = scrape_itchio_games(tag=tag, page=page)
            results.extend(itchio_games)
        except Exception as e:
            logger.error(f"Error retrieving itch.io catalog: {e}", exc_info=True)

    return results


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

    # Determine media type
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
