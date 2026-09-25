import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.scanner.base import ReviewStatus, ScanResult
from app.scanner.clamav import ClamAVScanner
from app.scanner.composite import CompositeScanner
from app.scanner.virustotal import VirusTotalScanner, VTRateLimiter


@pytest.fixture
def dummy_apk(tmp_path):
    apk_file = tmp_path / "game_test.apk"
    apk_file.write_bytes(b"PK\x03\x04DUMMY_APK_CONTENT_FOR_SECURITY_SCANNING")
    return apk_file


def test_virustotal_hash_lookup_approved(dummy_apk):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "attributes": {
                "last_analysis_stats": {
                    "harmless": 45,
                    "malicious": 0,
                    "suspicious": 1,
                    "undetected": 20,
                }
            }
        }
    }

    limiter = VTRateLimiter(interval_seconds=0.01)
    scanner = VirusTotalScanner(api_key="mock_vt_key", threshold=2, rate_limiter=limiter)

    with patch("requests.get", return_value=mock_resp):
        res = scanner.scan_apk(dummy_apk)
        assert res.scanner_name == "virustotal"
        assert res.positives == 1  # 0 malicious + 1 suspicious <= threshold (2)
        assert res.status == ReviewStatus.APPROVED
        assert res.total_engines == 66


def test_virustotal_hash_lookup_rejected_over_threshold(dummy_apk):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": {
            "attributes": {
                "last_analysis_stats": {
                    "harmless": 20,
                    "malicious": 3,  # > 2 threshold!
                    "suspicious": 0,
                    "undetected": 10,
                }
            }
        }
    }

    limiter = VTRateLimiter(interval_seconds=0.01)
    scanner = VirusTotalScanner(api_key="mock_vt_key", threshold=2, rate_limiter=limiter)

    with patch("requests.get", return_value=mock_resp):
        res = scanner.scan_apk(dummy_apk)
        assert res.positives == 3
        assert res.status == ReviewStatus.REJECTED


def test_virustotal_hash_404_upload_and_poll(dummy_apk):
    # 1. Lookup 404 (file not on VT yet)
    lookup_404 = MagicMock(status_code=404)

    # 2. Upload file
    upload_resp = MagicMock(status_code=200)
    upload_resp.json.return_value = {"data": {"id": "analysis_id_12345"}}

    # 3. Poll analysis
    poll_resp = MagicMock(status_code=200)
    poll_resp.json.return_value = {
        "data": {
            "attributes": {
                "status": "completed",
                "stats": {"malicious": 0, "suspicious": 0, "harmless": 50},
            }
        }
    }

    limiter = VTRateLimiter(interval_seconds=0.01)
    scanner = VirusTotalScanner(
        api_key="mock_vt_key",
        threshold=2,
        rate_limiter=limiter,
        max_poll_attempts=3,
        poll_interval_seconds=0.01,
    )

    with patch("requests.get", side_effect=[lookup_404, poll_resp]):
        with patch("requests.post", return_value=upload_resp):
            res = scanner.scan_apk(dummy_apk)
            assert res.status == ReviewStatus.APPROVED
            assert res.positives == 0


def test_virustotal_no_api_key_pending(dummy_apk):
    scanner = VirusTotalScanner(api_key="")
    res = scanner.scan_apk(dummy_apk)
    assert res.status == ReviewStatus.PENDING
    assert "not configured" in res.details.get("reason", "")


def test_clamav_scanner_clean(dummy_apk):
    scanner = ClamAVScanner(clamscan_path="/usr/bin/clamscan")
    mock_proc = MagicMock(returncode=0, stdout="test.apk: OK\n")

    with patch("subprocess.run", return_value=mock_proc):
        res = scanner.scan_apk(dummy_apk)
        assert res.status == ReviewStatus.APPROVED
        assert res.positives == 0


def test_clamav_scanner_infected(dummy_apk):
    scanner = ClamAVScanner(clamscan_path="/usr/bin/clamscan")
    mock_proc = MagicMock(returncode=1, stdout="test.apk: Android.Trojan.Dropper FOUND\n")

    with patch("subprocess.run", return_value=mock_proc):
        res = scanner.scan_apk(dummy_apk)
        assert res.status == ReviewStatus.REJECTED
        assert res.positives == 1


def test_composite_scanner_short_circuit(dummy_apk):
    clamav = ClamAVScanner(clamscan_path="/usr/bin/clamscan")
    vt = VirusTotalScanner(api_key="mock_key")

    mock_clam_infected = MagicMock(returncode=1, stdout="Infected")

    # ClamAV detects infection; VT should NEVER be called
    with patch("subprocess.run", return_value=mock_clam_infected):
        with patch.object(vt, "scan_apk") as mock_vt_scan:
            composite = CompositeScanner([clamav, vt])
            res = composite.scan_apk(dummy_apk)
            assert res.status == ReviewStatus.REJECTED
            assert res.scanner_name == "clamav"
            mock_vt_scan.assert_not_called()
