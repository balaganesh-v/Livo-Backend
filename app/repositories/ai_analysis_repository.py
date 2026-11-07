from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.file_ai_analysis import FileAIAnalysis


class AIAnalysisRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_by_file_id(self, file_id: int) -> FileAIAnalysis | None:
        return self.session.scalar(
            select(FileAIAnalysis).where(FileAIAnalysis.file_id == file_id)
        )

    def get_file_ids_with_analysis(self, file_ids: list[int]) -> set[int]:
        if not file_ids:
            return set()
        statement = select(FileAIAnalysis.file_id).where(
            FileAIAnalysis.file_id.in_(file_ids)
        )
        return set(self.session.scalars(statement))

    def save(self, file_id: int, result: dict) -> FileAIAnalysis:
        record = self.get_by_file_id(file_id)
        if record is None:
            record = FileAIAnalysis(file_id=file_id)
            self.session.add(record)
        for field, value in result.items():
            setattr(record, field, value)
        self.session.commit()
        self.session.refresh(record)
        return record
