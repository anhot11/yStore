import base64
import hashlib
import hmac
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

from app.cache import cache_image, register_image_url
from app.config import (
    CACHE_DIR,
    GITHUB_WEBHOOK_SECRET,
    HTTP_TIMEOUT,
    STAGING_DIR,
    USER_AGENT,
)
from app.publisher_db import upsert_listing
from app.scanner import get_default_scanner
from app.scanner.base import ReviewStatus, ScanResult

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def verify_github_signature(
    payload_bytes: bytes,
    signature_header: Optional[str],
    secret: Optional[str] = None,
) -> bool:
    """Verify GitHub HMAC-SHA256 webhook signature."""
    sec = secret or GITHUB_WEBHOOK_SECRET
    if not signature_header or not sec:
        return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    expected_sig = hmac.new(
        sec.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    received_sig = signature_header[len(prefix):]
    return hmac.compare_digest(expected_sig, received_sig)


def fetch_github_file(
    owner: str,
    repo: str,
    file_path: str,
    ref: Optional[str] = None,
    token: Optional[str] = None,
) -> Optional[bytes]:
    """Fetch raw file content from GitHub repository at a specific ref/tag."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{file_path}"
    params = {"ref": ref} if ref else {}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github.raw+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=HTTP_TIMEOUT)
        if resp.status_code == 200:
            return resp.content
        return None
    except Exception as e:
        logger.warning(f"Failed to fetch {file_path} from {owner}/{repo}: {e}")
        return None


def validate_metadata(
    title: str,
    short_desc: str,
    full_desc: str,
    icon_bytes: Optional[bytes],
) -> Tuple[bool, List[str]]:
    """Validate fastlane metadata structure rules."""
    errors = []
    if not title or not title.strip():
        errors.append("title.txt must not be empty")
    if not short_desc and not full_desc:
        errors.append("Either short_description.txt or full_description.txt must be provided")
    if not icon_bytes or len(icon_bytes) < 8:
        errors.append("icon.png must be present and non-empty")

    return len(errors) == 0, errors


def download_apk_asset(
    asset_download_url: str,
    target_path: Path,
    token: Optional[str] = None,
) -> str:
    """Download APK asset from GitHub Release and return its SHA256."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/octet-stream",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    resp = requests.get(asset_download_url, headers=headers, stream=True, timeout=HTTP_TIMEOUT * 4)
    resp.raise_for_status()

    sha = hashlib.sha256()
    temp_target = target_path.with_suffix(".downloading")
    with open(temp_target, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)
                sha.update(chunk)

    temp_target.replace(target_path)
    return sha.hexdigest()


def process_release_webhook(
    payload: Dict[str, Any],
    token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Process incoming 'release published' webhook event:
    1. Parse repo & release information.
    2. Check for .apk release asset.
    3. Read and validate Fastlane metadata files.
    4. Download APK to staging.
    5. Run modular Security Scanner (VirusTotal).
    6. Update listing status (pending, approved, rejected) in database.
    """
    action = payload.get("action")
    if action not in ("published", "created", "released"):
        logger.info(f"Ignoring release action: {action}")
        return {"status": "ignored", "reason": f"Action '{action}' is not 'published'"}

    repository = payload.get("repository", {})
    owner = repository.get("owner", {}).get("login")
    repo_name = repository.get("name")
    full_repo = f"{owner}/{repo_name}"

    release = payload.get("release", {})
    tag_name = release.get("tag_name", "latest")
    assets = release.get("assets", [])

    # Step 2: Locate APK asset
    apk_asset = None
    for asset in assets:
        if asset.get("name", "").lower().endswith(".apk"):
            apk_asset = asset
            break

    if not apk_asset:
        logger.warning(f"No .apk asset found in release {tag_name} for {full_repo}")
        return {"status": "rejected", "error": "No .apk asset attached to the release"}

    apk_name = apk_asset.get("name")
    apk_url = apk_asset.get("browser_download_url") or apk_asset.get("url")

    # Step 3: Read metadata files from repository
    logger.info(f"Reading Fastlane metadata for {full_repo} at tag {tag_name}...")
    title_bytes = fetch_github_file(owner, repo_name, "metadata/android/en-US/title.txt", ref=tag_name, token=token)
    short_desc_bytes = fetch_github_file(owner, repo_name, "metadata/android/en-US/short_description.txt", ref=tag_name, token=token)
    full_desc_bytes = fetch_github_file(owner, repo_name, "metadata/android/en-US/full_description.txt", ref=tag_name, token=token)
    icon_bytes = fetch_github_file(owner, repo_name, "metadata/android/en-US/images/icon.png", ref=tag_name, token=token)

    title = title_bytes.decode("utf-8").strip() if title_bytes else ""
    short_desc = short_desc_bytes.decode("utf-8").strip() if short_desc_bytes else ""
    full_desc = full_desc_bytes.decode("utf-8").strip() if full_desc_bytes else ""

    # Validate metadata schema
    is_valid, validation_errors = validate_metadata(title, short_desc, full_desc, icon_bytes)
    if not is_valid:
        logger.warning(f"Metadata validation failed for {full_repo}: {validation_errors}")
        return {
            "status": "rejected",
            "error": "Metadata validation failed",
            "details": validation_errors,
        }

    # Save icon to local cache
    icon_url: Optional[str] = None
    if icon_bytes:
        icon_filename = f"pub_{owner}_{repo_name}_icon.png"
        icon_path = CACHE_DIR / icon_filename
        icon_path.write_bytes(icon_bytes)
        icon_url = f"/cache/{icon_filename}"

    # Step 4: Download APK to staging
    staging_file = STAGING_DIR / f"{owner}_{repo_name}_{tag_name}.apk"
    logger.info(f"Downloading release APK from {apk_url}...")
    sha256 = download_apk_asset(apk_url, staging_file, token=token)

    # Step 5: Run Security Scan
    logger.info(f"Running security scan on APK (SHA256: {sha256})...")
    scanner = get_default_scanner()
    scan_result: ScanResult = scanner.scan_apk(staging_file, sha256=sha256)

    # Step 6: Save listing with review status
    listing_id = f"{owner}.{repo_name}"
    upsert_listing(
        listing_id=listing_id,
        publisher_id=owner,
        repo=full_repo,
        tag=tag_name,
        version_code=tag_name.lstrip("v"),
        title=title,
        short_description=short_desc,
        full_description=full_desc,
        icon_url=icon_url,
        screenshots=[],
        changelog=release.get("body", ""),
        apk_download_url=apk_url,
        sha256=sha256,
        status=scan_result.status,
        positives=scan_result.positives,
        total_engines=scan_result.total_engines,
        scanner_details=scan_result.details,
    )

    logger.info(
        f"Listing {listing_id} updated with status: {scan_result.status.value} "
        f"(detections: {scan_result.positives}/{scan_result.total_engines})"
    )

    return {
        "status": scan_result.status.value,
        "listing_id": listing_id,
        "title": title,
        "sha256": sha256,
        "positives": scan_result.positives,
        "total_engines": scan_result.total_engines,
    }
