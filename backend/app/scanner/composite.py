import logging
from pathlib import Path
from typing import List, Optional

from app.scanner.base import ReviewStatus, ScanResult, SecurityScanner

logger = logging.getLogger(__name__)


class CompositeScanner(SecurityScanner):
    """
    Tiered composite scanner.
    Runs fast local scanners (e.g. ClamAV) first; if rejected, stops immediately.
    Otherwise advances to next tier (e.g. VirusTotal).
    """

    def __init__(self, scanners: List[SecurityScanner]):
        self.scanners = scanners

    def scan_apk(self, file_path: Path, sha256: Optional[str] = None) -> ScanResult:
        last_result: Optional[ScanResult] = None

        for scanner in self.scanners:
            logger.info(f"Running scanner tier: {scanner.__class__.__name__}")
            result = scanner.scan_apk(file_path, sha256=sha256)
            last_result = result

            # Short-circuit on rejection
            if result.status == ReviewStatus.REJECTED:
                logger.warning(
                    f"APK rejected by {result.scanner_name} (positives: {result.positives}); short-circuiting"
                )
                return result

        if last_result is None:
            raise RuntimeError("No scanners configured in CompositeScanner")

        return last_result
