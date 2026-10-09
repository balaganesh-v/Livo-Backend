"""HTTP endpoint for manually triggering file AI analysis."""

import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.ai_analysis import AIAnalysisResponse
from app.services.ai_analysis_service import (
    AIAnalysisError,
    AIAnalysisService,
    DocumentEngineUnavailableError,
    NoExtractedContentError,
    UnsupportedFileTypeError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai-analysis", tags=["ai-analysis"])
ai_analysis_service = AIAnalysisService()


@router.post("/{file_id}", response_model=AIAnalysisResponse)
def analyze_file(file_id: int) -> AIAnalysisResponse:
    try:
        result = ai_analysis_service.analyze_file(file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="File record or file path was not found") from exc
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except NoExtractedContentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DocumentEngineUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIAnalysisError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        logger.exception("Database operation failed during AI analysis")
        raise HTTPException(status_code=500, detail="AI analysis persistence failed") from exc
    except Exception as exc:
        logger.exception("Unexpected AI analysis failure for file_id=%s", file_id)
        raise HTTPException(status_code=500, detail="AI analysis failed unexpectedly") from exc
    return AIAnalysisResponse(file_id=file_id, analysis=result)
