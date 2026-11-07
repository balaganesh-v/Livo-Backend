
from datetime import datetime, timezone
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.file_processing.extraction.content_extractor import (
    EXTRACTOR_NAME,
    SUPPORTED_EXTENSIONS,
    ContentExtractionError,
    extract_file_content,
    validate_file_path,
)
from app.models.file_content import FileContent
from app.repositories.file_content_repository import FileContentRepository
from app.repositories.file_repository import FileRepository


class FileNotFoundInDatabaseError(Exception):
    pass


class FileContentService:
    def __init__(self, session: Session):
        self.session = session
        self.file_repository = FileRepository(session)
        self.content_repository = FileContentRepository(session)

    def extract_content_for_scanned_file(
        self,
        file_id: int,
        user_id: int,
    ) -> FileContent:
        # Step 1: Find the file and check its owner.
        file_record = self.file_repository.get_file_by_id(
            file_id,
            user_id,
        )

        if file_record is None:
            raise FileNotFoundInDatabaseError

        # A file row is only authorized through a source folder owned by the
        # same authenticated user. Do not trust a stale or inconsistent FK.
        if (
            file_record.source_folder is None
            or file_record.source_folder.user_id != user_id
        ):
            raise FileNotFoundInDatabaseError

        # Step 2: Find or create the content record.
        content_record = (
            self.content_repository.get_or_create_file_content_record(
                file_id
            )
        )

        file_extension = Path(file_record.file_path).suffix.lower()
        selected_extractor = (
            f"{EXTRACTOR_NAME}:{file_extension.lstrip('.')}"
            if file_extension in SUPPORTED_EXTENSIONS
            else f"{EXTRACTOR_NAME}:unsupported"
        )
        logger = logging.getLogger(__name__)
        logger.info(
            "Starting content extraction file_id=%s file_name=%s extension=%s",
            file_id,
            file_record.name,
            file_extension,
        )

        # Step 3: Check whether this file type is supported.
        if file_extension not in SUPPORTED_EXTENSIONS:
            logger.warning("Unsupported file format file_id=%s", file_id)
            content_record.extracted_text = None
            content_record.extraction_status = "unsupported"
            content_record.extraction_error = (
                "This file format is not supported."
            )
        else:
            # Step 4: Validate the file path and extract its content.
            try:
                safe_path = validate_file_path(
                    file_record.file_path,
                    file_record.source_folder.folder_path,
                )
                logger.info(
                    "Selected extractor=%s file_id=%s",
                    selected_extractor,
                    file_id,
                )
                extraction_result = extract_file_content(safe_path)

                content_record.extracted_text = extraction_result[
                    "extracted_text"
                ]
                content_record.extraction_status = extraction_result[
                    "extraction_status"
                ]
                content_record.extraction_error = (
                    None
                    if content_record.extraction_status == "truncated"
                    else extraction_result["error"]
                )
                if content_record.extraction_status == "failed":
                    content_record.extracted_text = None

            except ContentExtractionError as exc:
                content_record.extracted_text = None
                content_record.extraction_status = "failed"
                content_record.extraction_error = str(exc)
                logger.warning(
                    "Original file validation failed file_id=%s reason=%s",
                    file_id,
                    str(exc),
                )
            except Exception:
                content_record.extracted_text = None
                content_record.extraction_status = "failed"
                content_record.extraction_error = "File content could not be extracted."
                logger.exception("Extraction failed file_id=%s", file_id)

        logger.info(
            "Extraction finished file_id=%s status=%s characters=%s",
            file_id,
            content_record.extraction_status,
            len(content_record.extracted_text or ""),
        )

        # Step 5: Save the extraction result.
        content_record.extractor_name = selected_extractor
        content_record.extracted_at = datetime.now(
            timezone.utc
        ).replace(tzinfo=None)

        try:
            self.session.commit()
            self.session.refresh(content_record)
            logger.info("Extraction saved file_id=%s", file_id)
        except Exception:
            self.session.rollback()
            logger.exception("Extraction persistence failed file_id=%s", file_id)
            raise

        return content_record

    def get_extracted_content(
        self,
        file_id: int,
        user_id: int,
    ) -> FileContent:
        # Check that the requested file belongs to this user.
        file_record = self.file_repository.get_file_by_id(
            file_id,
            user_id,
        )

        if file_record is None:
            raise FileNotFoundInDatabaseError

        # Return the content saved for that file.
        content_record = (
            self.content_repository.get_file_content_by_file_id(
                file_id
            )
        )

        if content_record is None:
            raise FileNotFoundInDatabaseError

        return content_record
