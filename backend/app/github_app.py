import base64
import logging
import time
from typing import Any, Dict, List, Optional
import jwt
import requests

from app.config import (
    BACKEND_PUBLIC_URL,
    GITHUB_APP_ID,
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
    GITHUB_PRIVATE_KEY,
    GITHUB_WEBHOOK_SECRET,
    HTTP_TIMEOUT,
    USER_AGENT,
)
from app.publisher_db import upsert_publisher

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"

# Minimal 1x1 valid PNG in base64 as placeholder icon and screenshot
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def generate_app_jwt(
    app_id: Optional[str] = None,
    private_key_pem: Optional[str] = None
) -> str:
    """Generate RS256 JWT for GitHub App authentication."""
    aid = app_id or GITHUB_APP_ID
    key = private_key_pem or GITHUB_PRIVATE_KEY

    if not aid or not key:
        raise ValueError("GITHUB_APP_ID and GITHUB_PRIVATE_KEY must be configured")

    now = int(time.time())
    payload = {
        "iat": now - 60,  # 60s in the past to prevent clock drift issues
        "exp": now + 540,  # 9 minutes expiration (max 10 min allowed)
        "iss": aid,
    }
    encoded_jwt = jwt.encode(payload, key, algorithm="RS256")
    return encoded_jwt


def get_installation_access_token(
    installation_id: str,
    app_id: Optional[str] = None,
    private_key_pem: Optional[str] = None,
) -> str:
    """Obtain an installation access token to act with permissions (contents:write, administration:write)."""
    app_jwt = generate_app_jwt(app_id, private_key_pem)
    headers = {
        "Authorization": f"Bearer {app_jwt}",
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    url = f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
    resp = requests.post(url, headers=headers, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data["token"]


def exchange_oauth_code(code: str) -> Dict[str, Any]:
    """Exchange GitHub App OAuth web flow authorization code for user access token."""
    url = "https://github.com/login/oauth/access_token"
    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    payload = {
        "client_id": GITHUB_CLIENT_ID,
        "client_secret": GITHUB_CLIENT_SECRET,
        "code": code,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def get_github_user(token: str) -> Dict[str, Any]:
    """Retrieve authenticated GitHub user profile."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    resp = requests.get(f"{GITHUB_API_BASE}/user", headers=headers, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def register_repo_webhook(
    token: str,
    owner: str,
    repo: str,
    webhook_url: Optional[str] = None,
    webhook_secret: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Register webhook in developer's repository listening for 'release' published event.
    Requires administration:write permission.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/hooks"
    target_url = webhook_url or f"{BACKEND_PUBLIC_URL.rstrip('/')}/webhooks/github"
    secret = webhook_secret or GITHUB_WEBHOOK_SECRET

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    payload = {
        "name": "web",
        "active": True,
        "events": ["release"],
        "config": {
            "url": target_url,
            "content_type": "json",
            "secret": secret,
            "insecure_ssl": "0",
        },
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def create_fastlane_metadata_template(
    token: str,
    owner: str,
    repo: str,
    title: str = "My Awesome Game",
    short_desc: str = "Fast-paced Android game.",
    full_desc: str = "Detailed description of the game with features and gameplay instructions.",
) -> None:
    """
    Commit the Fastlane / F-Droid style metadata structure to the repo:
    /metadata/android/en-US/title.txt
    /metadata/android/en-US/short_description.txt
    /metadata/android/en-US/full_description.txt
    /metadata/android/en-US/images/icon.png
    /metadata/android/en-US/images/phoneScreenshots/screenshot_1.png
    /metadata/android/en-US/changelogs/1.txt
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }

    files_to_commit = {
        "metadata/android/en-US/title.txt": base64.b64encode(title.encode("utf-8")).decode("utf-8"),
        "metadata/android/en-US/short_description.txt": base64.b64encode(short_desc.encode("utf-8")).decode("utf-8"),
        "metadata/android/en-US/full_description.txt": base64.b64encode(full_desc.encode("utf-8")).decode("utf-8"),
        "metadata/android/en-US/images/icon.png": TINY_PNG_B64,
        "metadata/android/en-US/images/phoneScreenshots/screenshot_1.png": TINY_PNG_B64,
        "metadata/android/en-US/changelogs/1.txt": base64.b64encode(b"Initial v1 release").decode("utf-8"),
        "README.md": base64.b64encode(
            (
                f"# {title}\n\n"
                "Published via **yStore**.\n\n"
                "## How to Publish Updates\n"
                "1. Update the metadata files under `metadata/android/en-US/`.\n"
                "2. Create a new GitHub Release with a tag (e.g. `v1.0.0`).\n"
                "3. Attach your `.apk` file as an asset to the Release.\n"
                "4. yStore webhook will automatically scan and publish the game.\n"
            ).encode("utf-8")
        ).decode("utf-8"),
    }

    for path, content_b64 in files_to_commit.items():
        url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}"
        payload = {
            "message": f"chore: initialize {path}",
            "content": content_b64,
            "branch": "main",
        }
        resp = requests.put(url, headers=headers, json=payload, timeout=HTTP_TIMEOUT)
        if resp.status_code not in (200, 201):
            logger.warning(f"Failed to create template file {path}: {resp.status_code} {resp.text}")


def create_publisher_repo(
    token: str,
    repo_name: str,
    title: str = "My Android Game",
    short_desc: str = "An awesome game.",
    full_desc: str = "Detailed description.",
    installation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Full Publisher Onboarding Flow:
    1. Create GitHub repository with auto_init=True.
    2. Commit the Fastlane metadata template.
    3. Register webhook listening for 'release' published event.
    4. Save publisher record in database.
    """
    user_info = get_github_user(token)
    owner = user_info["login"]

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }

    # 1. Create Repository
    create_url = f"{GITHUB_API_BASE}/user/repos"
    create_payload = {
        "name": repo_name,
        "description": f"yStore metadata repository for {title}",
        "auto_init": True,
        "private": False,
    }
    resp = requests.post(create_url, headers=headers, json=create_payload, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    repo_data = resp.json()

    # Small sleep to ensure git ref is ready
    time.sleep(1.0)

    # 2. Commit Fastlane Metadata Structure
    create_fastlane_metadata_template(token, owner, repo_name, title, short_desc, full_desc)

    # 3. Register Webhook
    webhook_data = register_repo_webhook(token, owner, repo_name)

    # 4. Save Publisher in DB
    publisher_id = owner
    upsert_publisher(
        publisher_id=publisher_id,
        github_user=owner,
        repo_owner=owner,
        repo_name=repo_name,
        installation_id=installation_id,
    )

    return {
        "publisher_id": publisher_id,
        "owner": owner,
        "repo_name": repo_name,
        "repo_url": repo_data.get("html_url"),
        "webhook_id": webhook_data.get("id"),
        "metadata_structure": [
            "metadata/android/en-US/title.txt",
            "metadata/android/en-US/short_description.txt",
            "metadata/android/en-US/full_description.txt",
            "metadata/android/en-US/images/icon.png",
            "metadata/android/en-US/images/phoneScreenshots/screenshot_1.png",
            "metadata/android/en-US/changelogs/1.txt",
        ],
    }
