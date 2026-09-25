import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.getenv("YSTORE_CACHE_DIR", BASE_DIR / "cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# User-Agent header (identifiable, as requested)
USER_AGENT = os.getenv("YSTORE_USER_AGENT", "yStore-Aggregator/1.0 (+https://github.com/anhot11/yStore)")

# F-Droid
FDROID_REPO_URL = os.getenv("YSTORE_FDROID_REPO", "https://f-droid.org/repo")
FDROID_INDEX_URL = f"{FDROID_REPO_URL}/index-v2.json"
FDROID_CACHE_TTL_SECONDS = int(os.getenv("YSTORE_FDROID_CACHE_TTL", "3600"))

# itch.io
ITCHIO_BASE_URL = os.getenv("YSTORE_ITCHIO_BASE_URL", "https://itch.io")
ITCHIO_RATE_LIMIT_SECONDS = float(os.getenv("YSTORE_ITCHIO_RATE_LIMIT", "1.5"))

# Network timeouts
HTTP_TIMEOUT = int(os.getenv("YSTORE_HTTP_TIMEOUT", "15"))
