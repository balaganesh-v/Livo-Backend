from datetime import datetime

from sqlalchemy.orm import Session

from app.models.scan_job import ScanJob, ScanJobStatus


class ScanJobRepository:
    def create(self, session: Session, source_folder_id: int) -> ScanJob:
        job = ScanJob(source_folder_id=source_folder_id, status=ScanJobStatus.PENDING)
        session.add(job)
        session.flush()
        return job

    def mark_running(self, job: ScanJob) -> None:
        job.status = ScanJobStatus.RUNNING
        job.started_at = datetime.now()

    def update_progress(self, job: ScanJob, total: int, processed: int, failed: int) -> None:
        job.total_files = total
        job.processed_files = processed
        job.failed_files = failed

    def mark_completed(self, job: ScanJob) -> None:
        job.status = ScanJobStatus.COMPLETED
        job.completed_at = datetime.now()

    def mark_failed(self, job: ScanJob, error: str) -> None:
        job.status = ScanJobStatus.FAILED
        job.error_message = error[:60000]
        job.completed_at = datetime.now()

