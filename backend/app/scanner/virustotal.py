import hashlib
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

from app.config import (
    HTTP_TIMEOUT,
    USER_AGENT,
    VIRUSTOTAL_API_KEY,
    VIRUSTOTAL_MALICIOUS_THRESHOLD,
    VIRUSTOTAL_RATE_LIMIT_SECONDS,
)
from app.scanner.base import ReviewStatus, ScanResult, SecurityScanner

logger = logging.getLogger(__name__)

VT_BASE_URL = "https://www.virustotal.com/api/v3"


class VTRateLimiter:
    """Thread-safe rate limiter enforcing VirusTotal free-tier (4 req/min = 15s interval)."""

    def __init__(self, interval_seconds: float = VIRUSTOTAL_RATE_LIMIT_SECONDS):
        self.interval = interval_seconds
        self.last_time = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.time()
            elapsed = now - self.last_time
            if elapsed < self.interval:
                wait_time = self.interval - elapsed
                logger.debug(f"VirusTotal rate limiter: waiting {wait_time:.2f}s")
                time.sleep(wait_time)
            self.last_time = time.time()


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


class VirusTotalScanner(SecurityScanner):
    """
    VirusTotal v3 API security scanner with hash lookup, file upload,
    rate-limiting (4 req/min free tier), and polling.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        threshold: int = VIRUSTOTAL_MALICIOUS_THRESHOLD,
        rate_limiter: Optional[VTRateLimiter] = None,
        max_poll_attempts: int = 10,
        poll_interval_seconds: float = 15.0,
    ):
        self.api_key = api_key or VIRUSTOTAL_API_KEY
        self.threshold = threshold
        self.rate_limiter = rate_limiter or VTRateLimiter(VIRUSTOTAL_RATE_LIMIT_SECONDS)
        self.max_poll_attempts = max_poll_attempts
        self.poll_interval = poll_interval_seconds

    def _headers(self) -> Dict[str, str]:
        return {
            "x-apikey": self.api_key,
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

    def scan_apk(self, file_path: Path, sha256: Optional[str] = None) -> ScanResult:
        """
        Scan APK:
        1. Query VirusTotal by hash (GET /files/{hash}).
        2. If 404, upload file (POST /files) and poll report (GET /analyses/{id}).
        3. Block if detections > threshold (e.g. > 2).
        """
        if not file_path.exists():
            raise FileNotFoundError(f"APK file not found: {file_path}")

        file_hash = sha256 or compute_sha256(file_path)

        if not self.api_key:
            logger.warning("VirusTotal API key is not configured; setting scan status to pending")
            return ScanResult(
                scanner_name="virustotal",
                status=ReviewStatus.PENDING,
                positives=0,
                total_engines=0,
                sha256=file_hash,
                details={"reason": "VirusTotal API key not configured"},
                scanned_at=time.time(),
            )

        # Step 1: Hash lookup
        try:
            lookup_result = self._lookup_hash(file_hash)
            if lookup_result is not None:
                return lookup_result

            # Step 2: Upload file if not found
            logger.info(f"File {file_hash} not found in VirusTotal; uploading {file_path.name}...")
            analysis_id = self._upload_file(file_path)
            if not analysis_id:
                return ScanResult(
                    scanner_name="virustotal",
                    status=ReviewStatus.PENDING,
                    sha256=file_hash,
                    details={"error": "Upload failed to return analysis_id"},
                    scanned_at=time.time(),
                )

            # Step 3: Poll analysis report
            logger.info(f"Polling VirusTotal analysis report for {analysis_id}...")
            return self._poll_analysis(analysis_id, file_hash)

        except Exception as e:
            logger.error(f"Error during VirusTotal scan: {e}", exc_info=True)
            return ScanResult(
                scanner_name="virustotal",
                status=ReviewStatus.PENDING,
                sha256=file_hash,
                details={"error": str(e)},
                scanned_at=time.time(),
            )

    def _lookup_hash(self, file_hash: str) -> Optional[ScanResult]:
        """Query VirusTotal for existing file report by SHA256."""
        self.rate_limiter.acquire()
        url = f"{VT_BASE_URL}/files/{file_hash}"
        resp = requests.get(url, headers=self._headers(), timeout=HTTP_TIMEOUT)

        if resp.status_code == 404:
            return None  # File not in VirusTotal database

        if resp.status_code == 200:
            data = resp.json()
            return self._evaluate_vt_file_attributes(data.get("data", {}), file_hash)

        if resp.status_code == 429:
            logger.warning("VirusTotal rate limit exceeded during hash lookup")
            raise Exception("VirusTotal API rate limit exceeded (HTTP 429)")

        resp.raise_for_status()
        return None

    def _upload_file(self, file_path: Path) -> Optional[str]:
        """Upload APK to VirusTotal and return analysis ID."""
        self.rate_limiter.acquire()
        url = f"{VT_BASE_URL}/files"
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/vnd.android.package-archive")}
            resp = requests.post(url, headers=self._headers(), files=files, timeout=HTTP_TIMEOUT * 4)

        if resp.status_code in (200, 201):
            data = resp.json()
            return data.get("data", {}).get("id")

        if resp.status_code == 429:
            logger.warning("VirusTotal rate limit exceeded during upload")
            raise Exception("VirusTotal API rate limit exceeded (HTTP 429)")

        resp.raise_for_status()
        return None

    def _poll_analysis(self, analysis_id: str, file_hash: str) -> ScanResult:
        """Poll the analysis status until completed or max attempts reached."""
        url = f"{VT_BASE_URL}/analyses/{analysis_id}"

        for attempt in range(self.max_poll_attempts):
            self.rate_limiter.acquire()
            resp = requests.get(url, headers=self._headers(), timeout=HTTP_TIMEOUT)
            if resp.status_code == 200:
                data = resp.json().get("data", {})
                attributes = data.get("attributes", {})
                analysis_status = attributes.get("status")

                if analysis_status == "completed":
                    stats = attributes.get("stats", {})
                    malicious = stats.get("malicious", 0)
                    suspicious = stats.get("suspicious", 0)
                    positives = malicious + suspicious
                    total = sum(stats.values())

                    # Block if detections > threshold (e.g. > 2)
                    is_rejected = positives > self.threshold
                    status = ReviewStatus.REJECTED if is_rejected else ReviewStatus.APPROVED

                    return ScanResult(
                        scanner_name="virustotal",
                        status=status,
                        positives=positives,
                        total_engines=total,
                        sha256=file_hash,
                        permalink=f"https://www.virustotal.com/gui/file/{file_hash}",
                        details={"stats": stats, "results": attributes.get("results", {})},
                        scanned_at=time.time(),
                    )

            logger.info(f"VirusTotal analysis {analysis_id} pending (attempt {attempt + 1}/{self.max_poll_attempts})...")

        # If poll attempts exhausted before completion
        return ScanResult(
            scanner_name="virustotal",
            status=ReviewStatus.PENDING,
            sha256=file_hash,
            details={"warning": "Analysis still pending after maximum poll attempts"},
            scanned_at=time.time(),
        )

    def _evaluate_vt_file_attributes(self, file_data: Dict[str, Any], file_hash: str) -> ScanResult:
        """Evaluate VirusTotal file attributes against the threshold."""
        attrs = file_data.get("attributes", {})
        stats = attrs.get("last_analysis_stats", {})
        malicious = stats.get("malicious", 0)
        suspicious = stats.get("suspicious", 0)
        positives = malicious + suspicious
        total = sum(stats.values())

        # Block if detections > threshold (e.g. > 2)
        is_rejected = positives > self.threshold
        status = ReviewStatus.REJECTED if is_rejected else ReviewStatus.APPROVED

        return ScanResult(
            scanner_name="virustotal",
            status=status,
            positives=positives,
            total_engines=total,
            sha256=file_hash,
            permalink=f"https://www.virustotal.com/gui/file/{file_hash}",
            details={"stats": stats},
            scanned_at=time.time(),
        )
