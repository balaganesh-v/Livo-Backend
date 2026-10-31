
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.file_processing.metadata.file_metadata import FileMetadata
from app.file_processing.scanner.file_scanner import scan_folder
from app.models.file import File
from app.models.source_folder import SourceFolder, SourceFolderStatus


class FileRepository:
    def __init__(self, session: Session):
        self.session = session

    def discover_files_in_folder(self, folder_path: str | Path) -> list[Path]:
        return scan_folder(folder_path)

    def get_file_by_id(self, file_id: int, user_id: int) -> File | None:
        statement = (
            select(File)
            .options(joinedload(File.source_folder))
            .where(
                File.id == file_id,
                File.user_id == user_id,
            )
        )
        return self.session.scalar(statement)

    def get_source_folder_for_user(self, folder_id: int, user_id: int) -> SourceFolder | None:
        return self.session.scalar(
            select(SourceFolder).where(
                SourceFolder.id == folder_id,
                SourceFolder.user_id == user_id,
            )
        )

    def get_files_in_source_folder(self, folder_id: int, user_id: int) -> list[File]:
        statement = (
            select(File)
            .where(
                File.source_folder_id == folder_id,
                File.user_id == user_id,
                File.is_deleted.is_(False),
            )
            .order_by(File.id)
        )
        return list(self.session.scalars(statement))

    def get_source_folder_by_path(
        self,
        user_id: int,
        folder_path: str,
    ) -> SourceFolder | None:
        statement = select(SourceFolder).where(
            SourceFolder.user_id == user_id,
            SourceFolder.folder_path == folder_path,
        )
        return self.session.scalar(statement)

    def create_source_folder(
        self,
        user_id: int,
        folder_path: str,
    ) -> SourceFolder:
        source_folder = SourceFolder(
            user_id=user_id,
            name=Path(folder_path).name or folder_path,
            folder_path=folder_path,
            status=SourceFolderStatus.COMPLETED,
        )

        self.session.add(source_folder)
        self.session.flush()

        return source_folder

    def save_file_record(
        self,
        user_id: int,
        source_folder_id: int,
        metadata: FileMetadata,
        file_hash: str | None,
    ) -> File:
        statement = select(File).where(
            File.user_id == user_id,
            File.file_path == metadata.file_path,
        )
        file_record = self.session.scalar(statement)

        if file_record is None:
            file_record = File(
                user_id=user_id,
                source_folder_id=source_folder_id,
                name=metadata.name,
                file_path=metadata.file_path,
            )
            self.session.add(file_record)

        # Update the record whether it is new or already exists.
        file_record.source_folder_id = source_folder_id
        file_record.name = metadata.name
        file_record.file_path = metadata.file_path
        file_record.extension = metadata.extension
        file_record.mime_type = metadata.mime_type
        file_record.size_bytes = metadata.size_bytes
        file_record.file_hash = file_hash
        file_record.file_created_at = metadata.file_created_at.replace(
            tzinfo=None
        )
        file_record.file_modified_at = metadata.file_modified_at.replace(
            tzinfo=None
        )
        file_record.scanned_at = metadata.scanned_at.replace(tzinfo=None)
        file_record.is_deleted = False

        # Ensure the record has its database ID before returning it.
        self.session.flush()

        return file_record
