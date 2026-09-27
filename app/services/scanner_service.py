from pathlib import Path

from app.repositories.scanner_repository import ScannerRepository


class ScannerService:
    """Service layer for filesystem scanning."""

    def __init__(self, repository: ScannerRepository | None = None) -> None:
        self.repository = repository or ScannerRepository()

    def scan_folder(self, folder_path: str) -> list[Path]:
        """Scan a folder through the repository layer."""
        return self.repository.scan(folder_path)
