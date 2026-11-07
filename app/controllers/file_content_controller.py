
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_database_session
from app.file_processing.extraction.content_extractor import MAX_EXTRACTED_CHARS
from app.models.user import User
from app.schemas.file_content_schema import (
    FileContentResponse,
    FileContentTextResponse,
)
from app.security.authentication import get_current_user
from app.services.file_content_service import (
    FileContentService,
    FileNotFoundInDatabaseError,
)

router = APIRouter(prefix="/api/files", tags=["File Content"])


@router.post(
    "/{file_id}/extract-content",
    response_model=FileContentResponse,
)
def extract_content_for_file(
    file_id: int,
    session: Session = Depends(get_database_session),
    current_user: User = Depends(get_current_user),
) -> FileContentResponse:
    service = FileContentService(session)

    try:
        content_record = service.extract_content_for_scanned_file(
            file_id,
            current_user.id,
        )
    except FileNotFoundInDatabaseError:
        raise HTTPException(
            status_code=404,
            detail="File record not found.",
        )

    return FileContentResponse(
        file_id=content_record.file_id,
        file_name=content_record.file.name,
        file_type=content_record.file.extension,
        file_extension=content_record.file.extension,
        extraction_status=content_record.extraction_status,
        files_extracted=(1 if content_record.extraction_status in {"completed", "truncated"} else 0),
        records_persisted=1,
        failures=(
            1 if content_record.extraction_status in {"failed", "unsupported", "requires_ocr"} else 0
        ),
        character_count=len(content_record.extracted_text or ""),
        extracted_text=content_record.extracted_text,
        truncated=content_record.extraction_status == "truncated",
        message=(
            f"Extracted text was truncated at the configured {MAX_EXTRACTED_CHARS}-character limit."
            if content_record.extraction_status == "truncated"
            else content_record.extraction_error
        ),
        extractor_name=content_record.extractor_name,
        extracted_at=content_record.extracted_at,
        error=content_record.extraction_error,
    )


@router.get(
    "/{file_id}/content",
    response_model=FileContentTextResponse,
)
def get_extracted_content(
    file_id: int,
    session: Session = Depends(get_database_session),
    current_user: User = Depends(get_current_user),
) -> FileContentTextResponse:
    service = FileContentService(session)

    try:
        content_record = service.get_extracted_content(
            file_id,
            current_user.id,
        )
    except FileNotFoundInDatabaseError:
        raise HTTPException(
            status_code=404,
            detail="File or extracted content not found.",
        )

    return FileContentTextResponse(
        file_id=content_record.file_id,
        file_name=content_record.file.name,
        file_extension=content_record.file.extension,
        extraction_status=content_record.extraction_status,
        extracted_text=content_record.extracted_text,
        truncated=content_record.extraction_status == "truncated",
        extractor_name=content_record.extractor_name,
        extracted_at=content_record.extracted_at,
        message=(
            f"Extracted text was truncated at the configured {MAX_EXTRACTED_CHARS}-character limit."
            if content_record.extraction_status == "truncated"
            else content_record.extraction_error
        ),
        error=content_record.extraction_error,
    )
