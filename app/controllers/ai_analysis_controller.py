import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.connection import get_database_session
from app.models.user import User
from app.schemas.ai_analysis_schema import (
    AIAnalysisResponse,
    BulkAIAnalysisRequest,
    BulkAIAnalysisResponse,
)
from app.security.authentication import get_current_user
from app.services.ai_analysis_service import (
    AIAnalysisService,
    EmptyExtractedContentError,
    ExtractedContentUnavailableError,
    ExtractionFailedError,
    FileNotFoundForAnalysisError,
)
from app.services.ollama_service import (
    OllamaConnectionError,
    OllamaResponseError,
    OllamaTimeoutError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai-analysis", tags=["AI Analysis"])


@router.post("/bulk", response_model=BulkAIAnalysisResponse)
def analyze_source_folder(
    request: BulkAIAnalysisRequest,
    session: Session = Depends(get_database_session),
    current_user: User = Depends(get_current_user),
) -> BulkAIAnalysisResponse:
    service = AIAnalysisService(session)
    try:
        result = service.analyze_source_folder(
            request.source_folder_id,
            current_user.id,
            request.reanalyze,
        )
    except FileNotFoundForAnalysisError:
        raise HTTPException(status_code=404, detail="Source folder not found.")
    except SQLAlchemyError:
        session.rollback()
        logger.exception("Bulk AI analysis query failed folder_id=%s", request.source_folder_id)
        raise HTTPException(status_code=500, detail="Could not process source folder.")
    return BulkAIAnalysisResponse(**result)


@router.post("/{file_id}", response_model=AIAnalysisResponse)
def analyze_file(
    file_id: int,
    session: Session = Depends(get_database_session),
    current_user: User = Depends(get_current_user),
) -> AIAnalysisResponse:
    try:
        record = AIAnalysisService(session).analyze_file(file_id, current_user.id)
    except FileNotFoundForAnalysisError:
        raise HTTPException(status_code=404, detail="File not found.")
    except ExtractedContentUnavailableError:
        raise HTTPException(status_code=409, detail="Extracted content is unavailable.")
    except ExtractionFailedError:
        raise HTTPException(status_code=422, detail="File content extraction failed.")
    except EmptyExtractedContentError:
        raise HTTPException(status_code=422, detail="Extracted content is empty.")
    except OllamaTimeoutError:
        raise HTTPException(status_code=504, detail="Ollama analysis timed out.")
    except OllamaConnectionError:
        raise HTTPException(
            status_code=502,
            detail="Cannot connect to Ollama. Start Ollama and verify the configured model is available.",
        )
    except OllamaResponseError:
        raise HTTPException(status_code=502, detail="Ollama returned invalid analysis data.")
    except SQLAlchemyError:
        session.rollback()
        logger.exception("AI analysis persistence failed file_id=%s", file_id)
        raise HTTPException(status_code=500, detail="Could not save file analysis.")

    return AIAnalysisResponse(
        file_id=record.file_id,
        category=record.category,
        subcategory=record.subcategory,
        description=record.description,
        keywords=record.keywords,
        confidence=float(record.confidence),
        content_type=record.content_type,
        model_used=record.model_used,
    )
