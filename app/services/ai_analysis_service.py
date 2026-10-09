"""Orchestrate safe content extraction, provider analysis, validation, and storage."""

import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.ai.client import (
    AIClient,
    DoclingClient,
    DoclingProcessingError,
    DoclingUnavailableError,
)
from app.database.connection import SessionLocal
from app.models.file import File
from app.repositories.file_ai_analysis_repository import FileAIAnalysisRepository
from app.schemas.ai_analysis import AIAnalysisResult

logger = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json", ".xml", ".log", ".pdf", ".docx", ".xlsx",
    ".pptx", ".html", ".htm", ".xhtml", ".mhtml", ".mht", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
    ".bmp", ".webp", ".odt", ".ods", ".odp", ".epub", ".rtf", ".adoc", ".tex",
}


class AIAnalysisError(RuntimeError):
    """Expected failure safe to report to an API caller."""


class UnsupportedFileTypeError(AIAnalysisError):
    pass


class NoExtractedContentError(AIAnalysisError):
    pass


class DocumentEngineUnavailableError(AIAnalysisError):
    pass


class AIAnalysisService:
    def __init__(
        self,
        session_factory: sessionmaker[Session] = SessionLocal,
        client: AIClient | None = None,
        repository: FileAIAnalysisRepository | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.client = client
        self.repository = repository or FileAIAnalysisRepository()

    def analyze_file(self, file_id: int) -> AIAnalysisResult:
        logger.info("AI analysis started for file_id=%s", file_id)
        with self.session_factory() as session:
            file_record = session.scalar(select(File).where(File.id == file_id))
            if file_record is None:
                raise FileNotFoundError(file_id)
            extension = (file_record.extension or Path(file_record.file_path).suffix).lower()
            if extension not in SUPPORTED_EXTENSIONS:
                raise UnsupportedFileTypeError("This file type is not supported for text analysis")
            if not Path(file_record.file_path).is_file():
                raise FileNotFoundError(file_record.file_path)
            context: dict[str, object] = {
                "filename": file_record.name,
                "extension": extension,
                "mime_type": file_record.mime_type,
                "file_path": file_record.file_path,
                "file_size": file_record.size_bytes,
            }
            try:
                result, model_used = (self.client or DoclingClient()).analyze_file(context)
                result = AIAnalysisResult.model_validate(result)
                self.repository.upsert(
                    session, file_id=file_record.id, result=result, model_used=model_used
                )
                session.commit()
            except DoclingUnavailableError as exc:
                session.rollback()
                logger.exception("Docling is unavailable during analysis")
                raise DocumentEngineUnavailableError(str(exc)) from exc
            except DoclingProcessingError as exc:
                session.rollback()
                raise NoExtractedContentError(str(exc)) from exc
            except Exception as exc:
                session.rollback()
                if isinstance(exc, SQLAlchemyError):
                    logger.exception("AI analysis persistence failed for file_id=%s", file_id)
                    raise AIAnalysisError("Could not save AI analysis") from exc
                logger.exception("AI analysis failed for file_id=%s", file_id)
                raise
        logger.info("AI analysis completed for file_id=%s", file_id)
        return result
