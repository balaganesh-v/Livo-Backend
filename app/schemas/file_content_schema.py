
from datetime import datetime

from pydantic import BaseModel


class FileContentResponse(BaseModel):
    file_id: int
    file_name: str
    file_type: str | None
    file_extension: str | None
    extraction_status: str
    files_extracted: int
    records_persisted: int
    failures: int
    character_count: int
    extracted_text: str | None
    truncated: bool
    message: str | None
    extractor_name: str | None
    extracted_at: datetime | None
    error: str | None


class FileContentTextResponse(BaseModel):
    file_id: int
    file_name: str
    file_extension: str | None
    extraction_status: str
    extracted_text: str | None
    truncated: bool
    extractor_name: str | None
    extracted_at: datetime | None
    message: str | None
    error: str | None
