import hashlib
import logging
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from app.scanner.base import ReviewStatus, ScanResult, SecurityScanner

logger = logging.getLogger(__name__)


def compute_sha256(file_path: Path) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


class ClamAVScanner(SecurityScanner):
    """
    Local ClamAV scanner implementation.
    Acts as a high-throughput, low-latency first line of defense before VirusTotal.
    """

    def __init__(self, clamscan_path: Optional[str] = None):
        self.clamscan_bin = clamscan_path or shutil.which("clamscan")

    def scan_apk(self, file_path: Path, sha256: Optional[str] = None) -> ScanResult:
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_hash = sha256 or compute_sha256(file_path)

        if not self.clamscan_bin:
            logger.info("ClamAV binary (clamscan) not detected; marking clean fallback")
            return ScanResult(
                scanner_name="clamav",
                status=ReviewStatus.APPROVED,
                positives=0,
                total_engines=1,
                sha256=file_hash,
                details={"info": "ClamAV not installed on host; bypassed first-tier scan"},
                scanned_at=time.time(),
            )

        try:
            logger.info(f"Running ClamAV scan on {file_path}...")
            proc = subprocess.run(
                [self.clamscan_bin, "--no-summary", str(file_path)],
                capture_output=True,
                text=True,
                timeout=60,
            )

            # clamscan exit code 0 = clean, 1 = virus found, 2 = error
            if proc.returncode == 0:
                return ScanResult(
                    scanner_name="clamav",
                    status=ReviewStatus.APPROVED,
                    positives=0,
                    total_engines=1,
                    sha256=file_hash,
                    details={"output": proc.stdout.strip()},
                    scanned_at=time.time(),
                )
            elif proc.returncode == 1:
                logger.warning(f"ClamAV detected malware in {file_path}: {proc.stdout}")
                return ScanResult(
                    scanner_name="clamav",
                    status=ReviewStatus.REJECTED,
                    positives=1,
                    total_engines=1,
                    sha256=file_hash,
                    details={"virus": proc.stdout.strip()},
                    scanned_at=time.time(),
                )
            else:
                logger.error(f"ClamAV error (code {proc.returncode}): {proc.stderr}")
                return ScanResult(
                    scanner_name="clamav",
                    status=ReviewStatus.PENDING,
                    sha256=file_hash,
                    details={"error": proc.stderr.strip()},
                    scanned_at=time.time(),
                )

        except Exception as e:
            logger.error(f"Failed to execute ClamAV scan: {e}")
            return ScanResult(
                scanner_name="clamav",
                status=ReviewStatus.PENDING,
                sha256=file_hash,
                details={"error": str(e)},
                scanned_at=time.time(),
            )
