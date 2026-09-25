from app.scanner.base import ReviewStatus, ScanResult, SecurityScanner
from app.scanner.clamav import ClamAVScanner
from app.scanner.composite import CompositeScanner
from app.scanner.virustotal import VirusTotalScanner

_default_scanner: SecurityScanner = None


def get_default_scanner() -> SecurityScanner:
    global _default_scanner
    if _default_scanner is None:
        # Default chain: ClamAV (if present) -> VirusTotal
        clamav = ClamAVScanner()
        vt = VirusTotalScanner()
        _default_scanner = CompositeScanner([clamav, vt])
    return _default_scanner


def set_default_scanner(scanner: SecurityScanner) -> None:
    global _default_scanner
    _default_scanner = scanner
