from pathlib import Path

from app.services.scanner_service import ScannerService


class ScannerController:
    """Controller layer for filesystem scanning."""

    def __init__(self, service: ScannerService | None = None) -> None:
        self.service = service or ScannerService()

    def scan(self, folder_path: str) -> list[Path]:
        """Scan a folder through the service layer."""
        return self.service.scan_folder(folder_path)
