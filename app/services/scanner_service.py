from dataclasses import dataclass
from pathlib import Path

from app.file_processing.hashing.file_hash import calculate_file_hash
from app.file_processing.metadata.file_metadata import (
    FileMetadata,
    extract_file_metadata,
)
from app.repositories.scanner_repository import ScannerRepository


@dataclass(frozen=True, slots=True)
class ScannedFile:
    metadata: FileMetadata
    file_hash: str | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class FileScanResult:
    folder_path: str
    total_files: int
    processed_files: int
    failed_files: int
    files: list[ScannedFile]


class ScannerService:

    def __init__(self, repository: ScannerRepository | None = None) -> None:
        self.repository = repository or ScannerRepository()

    def scan(self, folder_path: str | Path) -> FileScanResult:
        paths = self.repository.scan(str(folder_path))
        results: list[ScannedFile] = []
        failed = 0
        processed = 0

        for path in paths:
            try:
                metadata = extract_file_metadata(path)
            except OSError:
                # A file may disappear or become inaccessible while scanning.
                failed += 1
                continue

            try:
                file_hash = calculate_file_hash(path)
            except OSError:
                failed += 1
                results.append(ScannedFile(metadata, None, "File could not be read"))
                continue

            results.append(ScannedFile(metadata, file_hash))
            processed += 1

        return FileScanResult(
            folder_path=str(Path(folder_path).expanduser().resolve()),
            total_files=len(paths),
            processed_files=processed,
            failed_files=failed,
            files=results,
        )
