from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class OrganizationPlanStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrganizationPlan(Base):
    __tablename__ = "organization_plans"

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    source_folder_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("source_folders.id", ondelete="CASCADE"),
        nullable=False,
    )

    scan_job_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("scan_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[OrganizationPlanStatus] = mapped_column(
        SAEnum(OrganizationPlanStatus),
        nullable=False,
        default=OrganizationPlanStatus.PENDING,
    )

    total_files: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    approved_files: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        server_onupdate=text("CURRENT_TIMESTAMP"),
    )

    user = relationship(
        "User",
        back_populates="organization_plans",
    )

    source_folder = relationship(
        "SourceFolder",
        back_populates="organization_plans",
    )

    scan_job = relationship(
        "ScanJob",
        back_populates="organization_plans",
    )

    items = relationship(
        "OrganizationPlanItem",
        back_populates="plan",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_op_user_id", "user_id"),
        Index("idx_op_status", "status"),
        Index("idx_op_scan_job_id", "scan_job_id"),
    )
