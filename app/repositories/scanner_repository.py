from pathlib import Path

from app.file_processing.scanner.file_scanner import scan_folder


class ScannerRepository:
    """Repository wrapper for filesystem scanning."""

    def scan(self, folder_path: str) -> list[Path]:
        """Return all files found under the supplied folder."""
        return scan_folder(folder_path)
