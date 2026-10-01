"""Request and response schemas for synchronous folder scans."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class FileScanRequest(BaseModel):
    folder_path: str = Field(min_length=1, max_length=2048)


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
    scan_job_id: int
    source_folder_id: int
    folder_path: str
    status: str
    total_files: int
    processed_files: int
    failed_files: int
