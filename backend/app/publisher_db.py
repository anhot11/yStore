import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional
from pathlib import Path

from app.config import DB_PATH
from app.models import GameItem
from app.scanner.base import ReviewStatus

logger = logging.getLogger(__name__)


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    """Initialize SQLite database tables for publishers and listings."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS publishers (
                id TEXT PRIMARY KEY,
                github_user TEXT NOT NULL,
                repo_owner TEXT NOT NULL,
                repo_name TEXT NOT NULL,
                installation_id TEXT,
                created_at REAL NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id TEXT PRIMARY KEY,
                publisher_id TEXT,
                repo TEXT NOT NULL,
                tag TEXT NOT NULL,
                version_code TEXT,
                title TEXT NOT NULL,
                short_description TEXT,
                full_description TEXT,
                icon_url TEXT,
                screenshots_json TEXT,
                changelog TEXT,
                apk_download_url TEXT,
                sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                positives INTEGER DEFAULT 0,
                total_engines INTEGER DEFAULT 0,
                scanner_details_json TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)
        conn.commit()


# Initialize database on module load
init_db()


def upsert_publisher(
    publisher_id: str,
    github_user: str,
    repo_owner: str,
    repo_name: str,
    installation_id: Optional[str] = None,
) -> None:
    now = time.time()
    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO publishers (id, github_user, repo_owner, repo_name, installation_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                github_user=excluded.github_user,
                repo_owner=excluded.repo_owner,
                repo_name=excluded.repo_name,
                installation_id=COALESCE(excluded.installation_id, publishers.installation_id)
        """, (publisher_id, github_user, repo_owner, repo_name, installation_id, now))
        conn.commit()


def get_publisher(publisher_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM publishers WHERE id = ?", (publisher_id,)).fetchone()
        return dict(row) if row else None


def upsert_listing(
    listing_id: str,
    publisher_id: Optional[str],
    repo: str,
    tag: str,
    version_code: Optional[str],
    title: str,
    short_description: str,
    full_description: str,
    icon_url: Optional[str],
    screenshots: List[str],
    changelog: str,
    apk_download_url: Optional[str],
    sha256: str,
    status: ReviewStatus,
    positives: int = 0,
    total_engines: int = 0,
    scanner_details: Optional[Dict[str, Any]] = None,
) -> None:
    now = time.time()
    screenshots_json = json.dumps(screenshots)
    details_json = json.dumps(scanner_details or {})

    with get_db_connection() as conn:
        conn.execute("""
            INSERT INTO listings (
                id, publisher_id, repo, tag, version_code, title, short_description,
                full_description, icon_url, screenshots_json, changelog, apk_download_url,
                sha256, status, positives, total_engines, scanner_details_json,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                tag=excluded.tag,
                version_code=excluded.version_code,
                title=excluded.title,
                short_description=excluded.short_description,
                full_description=excluded.full_description,
                icon_url=excluded.icon_url,
                screenshots_json=excluded.screenshots_json,
                changelog=excluded.changelog,
                apk_download_url=excluded.apk_download_url,
                sha256=excluded.sha256,
                status=excluded.status,
                positives=excluded.positives,
                total_engines=excluded.total_engines,
                scanner_details_json=excluded.scanner_details_json,
                updated_at=excluded.updated_at
        """, (
            listing_id, publisher_id, repo, tag, version_code, title,
            short_description, full_description, icon_url, screenshots_json,
            changelog, apk_download_url, sha256, status.value, positives,
            total_engines, details_json, now, now
        ))
        conn.commit()


def get_listing(listing_id: str) -> Optional[Dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if not row:
            return None
        res = dict(row)
        res["screenshots"] = json.loads(res.get("screenshots_json") or "[]")
        res["scanner_details"] = json.loads(res.get("scanner_details_json") or "{}")
        return res


def list_listings(
    status: Optional[ReviewStatus] = None,
    publisher_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    query = "SELECT * FROM listings WHERE 1=1"
    params: List[Any] = []
    if status:
        query += " AND status = ?"
        params.append(status.value)
    if publisher_id:
        query += " AND publisher_id = ?"
        params.append(publisher_id)

    query += " ORDER BY updated_at DESC"
    with get_db_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["screenshots"] = json.loads(item.get("screenshots_json") or "[]")
            item["scanner_details"] = json.loads(item.get("scanner_details_json") or "{}")
            result.append(item)
        return result


def get_approved_game_items() -> List[GameItem]:
    """Convert approved listings to unified GameItem model for catalog inclusion."""
    approved = list_listings(status=ReviewStatus.APPROVED)
    items = []
    for row in approved:
        description = row.get("short_description") or row.get("full_description") or ""
        items.append(
            GameItem(
                id=row["id"],
                title=row["title"],
                source="fdroid",  # Community/Fastlane standard format
                icon_url=row.get("icon_url"),
                screenshots=row.get("screenshots", []),
                description=description,
                developer=row.get("publisher_id") or row.get("repo", "").split("/")[0],
                download_url=row.get("apk_download_url"),
                tags=["Community", "Android"],
            )
        )
    return items
