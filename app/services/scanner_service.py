
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.file_processing.hashing.file_hash import calculate_file_hash
from app.file_processing.metadata.file_metadata import (
    FileMetadata,
    extract_file_metadata,
)
from app.models.source_folder import SourceFolderStatus
from app.repositories.file_repository import FileRepository


@dataclass
class ScannedFile:
    metadata: FileMetadata
    file_hash: str | None
    error: str | None = None
    file_id: int | None = None


@dataclass
class FileScanResult:
    folder_path: str
    total_files: int
    processed_files: int
    saved_files: int
    failed_files: int
    files: list[ScannedFile]


class ScannerService:
    def __init__(self, session: Session):
        self.session = session
        self.file_repository = FileRepository(session)

    def scan_folder_and_save_file_metadata(
        self,
        folder_path: str,
        user_id: int,
    ) -> FileScanResult:
        folder_path = str(Path(folder_path).expanduser().resolve())

        # Step 1: Find the files inside the selected folder.
        discovered_files = self.file_repository.discover_files_in_folder(
            folder_path
        )

        scanned_files = []
        processed_files = 0
        failed_files = 0

        # Step 2: Read metadata and calculate each file's hash.
        for file_path in discovered_files:
            try:
                metadata = extract_file_metadata(file_path)
            except OSError:
                failed_files += 1
                continue

            try:
                file_hash = calculate_file_hash(file_path)
                scanned_files.append(
                    ScannedFile(
                        metadata=metadata,
                        file_hash=file_hash,
                    )
                )
                processed_files += 1

            except OSError:
                failed_files += 1
                scanned_files.append(
                    ScannedFile(
                        metadata=metadata,
                        file_hash=None,
                        error="File could not be read to calculate its hash.",
                    )
                )

        # Step 3: Save or update the database records.
        try:
            source_folder = self.file_repository.get_source_folder_by_path(
                user_id,
                folder_path,
            )

            if source_folder is None:
                source_folder = self.file_repository.create_source_folder(
                    user_id,
                    folder_path,
                )

            saved_files = 0

            for scanned_file in scanned_files:
                file_record = self.file_repository.save_file_record(
                    user_id=user_id,
                    source_folder_id=source_folder.id,
                    metadata=scanned_file.metadata,
                    file_hash=scanned_file.file_hash,
                )

                scanned_file.file_id = file_record.id
                saved_files += 1

            source_folder.last_scanned_at = datetime.now(
                timezone.utc
            ).replace(tzinfo=None)

            source_folder.status = SourceFolderStatus.COMPLETED

            self.session.commit()

        except Exception:
            self.session.rollback()
            raise

        # Step 4: Return the scan summary.
        return FileScanResult(
            folder_path=folder_path,
            total_files=len(discovered_files),
            processed_files=processed_files,
            saved_files=saved_files,
            failed_files=failed_files,
            files=scanned_files,
        )
