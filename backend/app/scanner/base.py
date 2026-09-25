from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ScanResult(BaseModel):
    scanner_name: str
    status: ReviewStatus
    positives: int = 0
    total_engines: int = 0
    sha256: str
    permalink: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    scanned_at: float


class SecurityScanner(ABC):
    """Abstract base interface for interchangeable security scanners."""

    @abstractmethod
    def scan_apk(self, file_path: Path, sha256: Optional[str] = None) -> ScanResult:
        """
        Scan an APK file and return a ScanResult.
        file_path: Local filesystem path to the APK.
        sha256: Optional precomputed SHA256 of the file.
        """
        pass
