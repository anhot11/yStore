import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.getenv("YSTORE_CACHE_DIR", BASE_DIR / "cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

STAGING_DIR = CACHE_DIR / "staging"
STAGING_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.getenv("YSTORE_DB_PATH", CACHE_DIR / "ystore.db"))

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

# GitHub App Configuration (permissions: contents:write, administration:write)
GITHUB_APP_ID = os.getenv("GITHUB_APP_ID", "")
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_PRIVATE_KEY = os.getenv("GITHUB_PRIVATE_KEY", "")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "ystore-webhook-secret-key")
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")

# VirusTotal Scanner Configuration
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY", "")
# Block if > 2 engines mark malicious
VIRUSTOTAL_MALICIOUS_THRESHOLD = int(os.getenv("VIRUSTOTAL_MALICIOUS_THRESHOLD", "2"))
# 4 requests per minute free tier limit => 1 request every 15.0 seconds
VIRUSTOTAL_RATE_LIMIT_SECONDS = float(os.getenv("VIRUSTOTAL_RATE_LIMIT_SECONDS", "15.0"))
