"""Coordinate file discovery, metadata extraction, and hashing."""

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Callable

from app.file_processing.hashing.file_hash import calculate_file_hash
from app.file_processing.metadata.file_metadata import (
    FileMetadata,
    extract_file_metadata,
)
from app.file_processing.scanner.file_scanner import scan_folder

logger = logging.getLogger(__name__)


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


class FileScannerService:
    """Scan a folder and prepare file data for later persistence."""

    def scan(
        self,
        folder_path: str | Path,
        on_progress: Callable[[int, int, int, int], None] | None = None,
    ) -> FileScanResult:
        paths = scan_folder(folder_path)
        results: list[ScannedFile] = []
        failed = 0
        processed = 0
        if on_progress is not None:
            on_progress(len(paths), 0, 0, 0)
        for index, path in enumerate(paths, start=1):
            try:
                metadata = extract_file_metadata(path)
                try:
                    file_hash = calculate_file_hash(path)
                    results.append(ScannedFile(metadata, file_hash))
                    processed += 1
                except Exception as exc:
                    failed += 1
                    logger.warning("Could not hash scanned file %s: %s", path, exc)
                    results.append(ScannedFile(metadata, None, "File could not be read"))
            except Exception as exc:
                failed += 1
                # A file can disappear or become inaccessible during a scan.
                logger.warning("Could not read scanned file metadata %s: %s", path, exc)
            if on_progress is not None:
                on_progress(len(paths), index, processed, failed)

        return FileScanResult(
            folder_path=str(Path(folder_path).expanduser().resolve()),
            total_files=len(paths),
            processed_files=processed,
            failed_files=failed,
            files=results,
        )
