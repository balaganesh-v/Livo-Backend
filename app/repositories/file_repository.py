from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.file import File
from app.file_processing.metadata.file_metadata import FileMetadata


class FileRepository:
    def upsert_scanned_file(
        self,
        session: Session,
        *,
        user_id: int,
        source_folder_id: int,
        metadata: FileMetadata,
        file_hash: str | None,
    ) -> File:
        record = session.scalar(
            select(File).where(File.user_id == user_id, File.file_path == metadata.file_path)
        )
        if record is None:
            record = File(
                user_id=user_id,
                source_folder_id=source_folder_id,
                name=metadata.name,
                file_path=metadata.file_path,
            )
            session.add(record)
        record.source_folder_id = source_folder_id
        record.name = metadata.name
        record.extension = metadata.extension
        record.mime_type = metadata.mime_type
        record.size_bytes = metadata.size_bytes
        if file_hash is not None:
            record.file_hash = file_hash
        record.file_created_at = metadata.file_created_at
        record.file_modified_at = metadata.file_modified_at
        record.scanned_at = metadata.scanned_at
        return record
