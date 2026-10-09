"""Persistence operations for the one-to-one file AI analysis record."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.file_ai_analysis import FileAIAnalysis
from app.schemas.ai_analysis import AIAnalysisResult


class FileAIAnalysisRepository:
    def upsert(
        self,
        session: Session,
        *,
        file_id: int,
        result: AIAnalysisResult,
        model_used: str,
    ) -> FileAIAnalysis:
        analysis = session.scalar(
            select(FileAIAnalysis).where(FileAIAnalysis.file_id == file_id)
        )
        if analysis is None:
            analysis = FileAIAnalysis(file_id=file_id)
            session.add(analysis)
        analysis.category = result.category
        analysis.subcategory = result.subcategory
        analysis.description = result.description
        analysis.keywords = result.keywords
        analysis.confidence = result.confidence
        analysis.content_type = result.content_type
        analysis.is_personal = result.is_personal
        analysis.is_work_related = result.is_work
        analysis.is_study_related = result.is_study
        analysis.model_used = model_used
        analysis.analyzed_at = datetime.now()
        session.flush()
        return analysis
