"""Coordinate scan jobs, filesystem processing, and metadata persistence."""

import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.database.config import settings
from app.database.connection import SessionLocal
from app.models.scan_job import ScanJob
from app.models.source_folder import SourceFolderStatus
from app.models.user import User
from app.repositories.file_repository import FileRepository
from app.repositories.scan_job_repository import ScanJobRepository
from app.repositories.source_folder_repository import SourceFolderRepository
from app.services.file_scanner_service import FileScannerService

logger = logging.getLogger(__name__)


class ScanService:
    def __init__(
        self,
        session_factory: sessionmaker[Session] = SessionLocal,
        scanner: FileScannerService | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.scanner = scanner or FileScannerService()
        self.source_folders = SourceFolderRepository()
        self.scan_jobs = ScanJobRepository()
        self.files = FileRepository()

    def scan(self, folder_path: str) -> dict[str, int | str]:
        path = Path(folder_path).expanduser()
        if not path.exists():
            raise FileNotFoundError(folder_path)
        if not path.is_dir():
            raise NotADirectoryError(folder_path)
        resolved_path = str(path.resolve(strict=True))

        with self.session_factory() as session:
            job: ScanJob | None = None
            source_folder = None
            try:
                user = self._get_or_create_dev_user(session)
                source_folder = self.source_folders.get_or_create(session, user.id, resolved_path)
                job = self.scan_jobs.create(session, source_folder.id)
                session.commit()

                self.scan_jobs.mark_running(job)
                source_folder.status = SourceFolderStatus.SCANNING
                session.commit()

                def persist_progress(total: int, _index: int, processed: int, failed: int) -> None:
                    self.scan_jobs.update_progress(job, total, processed, failed)
                    session.commit()

                result = self.scanner.scan(resolved_path, on_progress=persist_progress)
                for item in result.files:
                    self.files.upsert_scanned_file(
                        session,
                        user_id=user.id,
                        source_folder_id=source_folder.id,
                        metadata=item.metadata,
                        file_hash=item.file_hash,
                    )
                self.scan_jobs.update_progress(
                    job, result.total_files, result.processed_files, result.failed_files
                )
                self.scan_jobs.mark_completed(job)
                source_folder.status = SourceFolderStatus.COMPLETED
                source_folder.last_scanned_at = datetime.now()
                session.commit()
                return {
                    "scan_job_id": job.id,
                    "source_folder_id": source_folder.id,
                    "folder_path": resolved_path,
                    "status": job.status.value,
                    "total_files": job.total_files,
                    "processed_files": job.processed_files,
                    "failed_files": job.failed_files,
                }
            except Exception as exc:
                logger.exception("Scan workflow failed for %s", resolved_path)
                session.rollback()
                if job is not None:
                    try:
                        self.scan_jobs.mark_failed(job, str(exc))
                        if source_folder is not None:
                            source_folder.status = SourceFolderStatus.FAILED
                        session.commit()
                    except SQLAlchemyError:
                        session.rollback()
                        logger.exception("Could not persist failed scan state")
                raise

    @staticmethod
    def _get_or_create_dev_user(session: Session) -> User:
        user = session.scalar(select(User).where(User.email == settings.dev_user_email))
        if user is None:
            user = User(
                name="Development User",
                email=settings.dev_user_email,
                password_hash="development-only-no-auth",
                is_active=True,
            )
            session.add(user)
            session.flush()
        return user
