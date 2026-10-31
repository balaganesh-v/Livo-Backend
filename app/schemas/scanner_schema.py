
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FolderScanRequest(BaseModel):
    folder_path: str = Field(min_length=1)


class ScannedFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_id: int | None = None
    name: str
    file_path: str
    extension: str | None
    mime_type: str | None
    size_bytes: int
    file_hash: str | None
    file_created_at: datetime
    file_modified_at: datetime
    scanned_at: datetime
    error: str | None = None


class FileScanResponse(BaseModel):
    folder_path: str
    files_discovered: int
    records_persisted: int
    total_files: int
    processed_files: int
    saved_files: int
    failed_files: int
    files: list[ScannedFileResponse]
