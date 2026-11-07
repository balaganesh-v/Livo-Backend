
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.file_content import FileContent


class FileContentRepository:
    def __init__(self, session: Session):
        self.session = session

    def get_file_content_by_file_id(
        self,
        file_id: int,
    ) -> FileContent | None:
        statement = select(FileContent).where(
            FileContent.file_id == file_id
        )

        return self.session.scalar(statement)

    def get_or_create_file_content_record(
        self,
        file_id: int,
    ) -> FileContent:
        content_record = self.get_file_content_by_file_id(file_id)

        if content_record is None:
            content_record = FileContent(file_id=file_id)
            self.session.add(content_record)

        return content_record
