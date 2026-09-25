import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch
import pytest

from app.scanner.base import ReviewStatus, ScanResult
from app.webhook import (
    process_release_webhook,
    validate_metadata,
    verify_github_signature,
)


def compute_test_sig(body: bytes, secret: str) -> str:
    h = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={h}"


def test_verify_github_signature_valid():
    secret = "my-test-secret"
    body = b'{"action": "published"}'
    sig = compute_test_sig(body, secret)
    assert verify_github_signature(body, sig, secret=secret) is True


def test_verify_github_signature_invalid():
    secret = "my-test-secret"
    body = b'{"action": "published"}'
    assert verify_github_signature(body, "sha256=invalidhash", secret=secret) is False
    assert verify_github_signature(body, None, secret=secret) is False


def test_validate_metadata_success():
    valid, errors = validate_metadata(
        title="Super Game",
        short_desc="Fun game",
        full_desc="Detailed game",
        icon_bytes=b"\x89PNG\r\n\x1a\nfakeimage",
    )
    assert valid is True
    assert errors == []


def test_validate_metadata_missing_title():
    valid, errors = validate_metadata(
        title="",
        short_desc="Fun game",
        full_desc="Detailed game",
        icon_bytes=b"\x89PNG\r\n\x1a\nfakeimage",
    )
    assert valid is False
    assert any("title" in e.lower() for e in errors)


def test_validate_metadata_missing_icon():
    valid, errors = validate_metadata(
        title="Super Game",
        short_desc="Fun game",
        full_desc="",
        icon_bytes=None,
    )
    assert valid is False
    assert any("icon" in e.lower() for e in errors)


def test_process_release_webhook_no_apk():
    payload = {
        "action": "published",
        "repository": {"owner": {"login": "dev1"}, "name": "game1"},
        "release": {
            "tag_name": "v1.0.0",
            "assets": [{"name": "source.zip", "browser_download_url": "http://example.com/source.zip"}],
        },
    }
    res = process_release_webhook(payload)
    assert res["status"] == "rejected"
    assert "No .apk asset" in res["error"]


def test_process_release_webhook_success_approved(tmp_path):
    payload = {
        "action": "published",
        "repository": {"owner": {"login": "indiedev"}, "name": "space-runner"},
        "release": {
            "tag_name": "v1.0.0",
            "assets": [
                {
                    "name": "SpaceRunner-v1.apk",
                    "browser_download_url": "https://github.com/indiedev/space-runner/releases/download/v1.0.0/SpaceRunner-v1.apk",
                }
            ],
            "body": "First release of Space Runner!",
        },
    }

    mock_scan_result = ScanResult(
        scanner_name="virustotal",
        status=ReviewStatus.APPROVED,
        positives=0,
        total_engines=65,
        sha256="abcdef1234567890",
        details={},
        scanned_at=1000.0,
    )

    with patch("app.webhook.fetch_github_file") as mock_fetch:
        # Mock file returns: title, short_desc, full_desc, icon
        mock_fetch.side_effect = [
            b"Space Runner",
            b"Fast space arcade",
            b"Full space arcade description",
            b"\x89PNG\r\n\x1a\nvalidpngheader",
        ]
        with patch("app.webhook.download_apk_asset", return_value="abcdef1234567890"):
            with patch("app.webhook.get_default_scanner") as mock_get_scanner:
                mock_scanner = MagicMock()
                mock_scanner.scan_apk.return_value = mock_scan_result
                mock_get_scanner.return_value = mock_scanner

                res = process_release_webhook(payload)
                assert res["status"] == "approved"
                assert res["title"] == "Space Runner"
                assert res["positives"] == 0


def test_webhook_endpoint_http(client):
    secret = "ystore-webhook-secret-key"
    payload = {"action": "published", "repository": {"name": "test"}}
    body = json.dumps(payload).encode("utf-8")
    sig = compute_test_sig(body, secret)

    # 1. Invalid signature => 401
    bad_res = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "release", "X-Hub-Signature-256": "sha256=wrong"},
    )
    assert bad_res.status_code == 401

    # 2. Non-release event => ignored
    ignored_res = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "push", "X-Hub-Signature-256": sig},
    )
    assert ignored_res.status_code == 200
    assert ignored_res.json()["status"] == "ignored"
