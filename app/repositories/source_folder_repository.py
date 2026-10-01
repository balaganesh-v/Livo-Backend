from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.source_folder import SourceFolder, SourceFolderStatus


class SourceFolderRepository:
    def get_or_create(self, session: Session, user_id: int, folder_path: str) -> SourceFolder:
        folder = session.scalar(
            select(SourceFolder).where(
                SourceFolder.user_id == user_id,
                SourceFolder.folder_path == folder_path,
            )
        )
        if folder is None:
            folder = SourceFolder(
                user_id=user_id,
                name=Path(folder_path).name or folder_path,
                folder_path=folder_path,
                status=SourceFolderStatus.ACTIVE,
            )
            session.add(folder)
            session.flush()
        return folder

