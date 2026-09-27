"""Request and response schemas for synchronous folder scans."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FileScanRequest(BaseModel):
    folder_path: str


class ScannedFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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
    total_files: int
    processed_files: int
    failed_files: int
    files: list[ScannedFileResponse]
