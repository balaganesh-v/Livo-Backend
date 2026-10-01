from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.base import Base


class ScanJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )

    source_folder_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("source_folders.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[ScanJobStatus] = mapped_column(
        # Keep enum labels aligned with the existing MySQL column, which stores
        # Python enum member names (PENDING, RUNNING, FAILED, etc.).
        SAEnum(ScanJobStatus),
        nullable=False,
        default=ScanJobStatus.PENDING,
    )

    total_files: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    processed_files: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    failed_files: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    source_folder = relationship(
        "SourceFolder",
        back_populates="scan_jobs",
    )

    organization_plans = relationship(
        "OrganizationPlan",
        back_populates="scan_job",
    )

    __table_args__ = (
        Index("idx_sj_source_folder_id", "source_folder_id"),
        Index("idx_sj_status", "status"),
    )
