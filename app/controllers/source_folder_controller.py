import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.connection import get_database_session
from app.models.user import User
from app.repositories.file_repository import FileRepository
from app.schemas.source_folder_processing_schema import (
    SourceFolderFileProcessResult,
    SourceFolderProcessResponse,
)
from app.security.authentication import get_current_user
from app.services.ai_analysis_service import (
    AIAnalysisService,
    EmptyExtractedContentError,
    ExtractedContentUnavailableError,
    ExtractionFailedError,
)
from app.services.file_content_service import FileContentService
from app.services.ollama_service import (
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/source-folders", tags=["Source Folders"])


@router.post(
    "/{source_folder_id}/process-files",
    response_model=SourceFolderProcessResponse,
)
def process_source_folder_files(
    source_folder_id: int,
    session: Session = Depends(get_database_session),
    current_user: User = Depends(get_current_user),
) -> SourceFolderProcessResponse:
    files = FileRepository(session)
    folder = files.get_source_folder_for_user(source_folder_id, current_user.id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Source folder not found.")

    folder_files = files.get_files_in_source_folder(source_folder_id, current_user.id)
    content_service = FileContentService(session)
    analysis_service = AIAnalysisService(session)
    results: list[SourceFolderFileProcessResult] = []
    extracted_count = 0
    categorized_count = 0
    unsupported_count = 0
    failed_count = 0

    for file_record in folder_files:
        extraction_status = "failed"
        category = None
        error = None
        try:
            content = content_service.extract_content_for_scanned_file(
                file_record.id,
                current_user.id,
            )
            extraction_status = content.extraction_status

            if extraction_status == "unsupported":
                unsupported_count += 1
                error = content.extraction_error or "This file format is not supported."
            elif extraction_status not in {"completed", "truncated"}:
                failed_count += 1
                error = content.extraction_error or (
                    f"Content extraction status is {extraction_status}."
                )
            else:
                extracted_count += 1
                analysis = analysis_service.analyze_file(
                    file_record.id,
                    current_user.id,
                )
                category = analysis.category
                categorized_count += 1
        except EmptyExtractedContentError:
            failed_count += 1
            error = "Extracted content is empty and cannot be categorized."
        except ExtractionFailedError:
            failed_count += 1
            error = "File content extraction failed."
        except ExtractedContentUnavailableError:
            failed_count += 1
            error = "Extracted content is unavailable for categorization."
        except OllamaTimeoutError:
            failed_count += 1
            error = "AI categorization timed out."
        except OllamaConnectionError:
            failed_count += 1
            error = "Could not connect to the configured AI service."
        except OllamaResponseError:
            failed_count += 1
            error = "AI service returned invalid categorization data."
        except SQLAlchemyError:
            session.rollback()
            failed_count += 1
            error = "A database error prevented this file from being processed."
            logger.exception("Folder file processing persistence failed file_id=%s", file_record.id)
        except Exception:
            session.rollback()
            failed_count += 1
            error = "This file could not be processed."
            logger.exception("Folder file processing failed file_id=%s", file_record.id)

        results.append(
            SourceFolderFileProcessResult(
                file_id=file_record.id,
                file_name=file_record.name,
                extraction_status=extraction_status,
                category=category,
                error=error,
            )
        )

    return SourceFolderProcessResponse(
        source_folder_id=source_folder_id,
        total_files=len(folder_files),
        extracted_files=extracted_count,
        categorized_files=categorized_count,
        unsupported_files=unsupported_count,
        failed_files=failed_count,
        results=results,
    )
