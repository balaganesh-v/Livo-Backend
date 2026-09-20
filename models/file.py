from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class File(Base):
    __tablename__ = "files"

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

    name: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )

    file_path: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    extension: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    mime_type: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    size_bytes: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        nullable=False,
        default=0,
    )

    file_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    file_created_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    file_modified_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    scanned_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    is_deleted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    deleted_at: Mapped[datetime | None] = mapped_column(
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
        back_populates="files",
    )

    source_folder = relationship(
        "SourceFolder",
        back_populates="files",
    )

    ai_analysis = relationship(
        "FileAIAnalysis",
        back_populates="file",
        uselist=False,
        cascade="all, delete-orphan",
    )

    document_summary = relationship(
        "DocumentSummary",
        back_populates="file",
        uselist=False,
        cascade="all, delete-orphan",
    )

    organization_plan_items = relationship(
        "OrganizationPlanItem",
        back_populates="file",
        cascade="all, delete-orphan",
    )

    duplicate_files = relationship(
        "DuplicateFile",
        back_populates="file",
        cascade="all, delete-orphan",
    )

    cleanup_recommendation = relationship(
        "CleanupRecommendation",
        back_populates="file",
        uselist=False,
        cascade="all, delete-orphan",
    )

    activity_logs = relationship(
        "ActivityLog",
        back_populates="file",
    )

    __table_args__ = (
        Index(
            "uq_files_user_path",
            "user_id",
            "file_path",
            unique=True,
            mysql_length={"file_path": 500},
        ),
        Index("idx_files_user_extension", "user_id", "extension"),
        Index("idx_files_user_deleted", "user_id", "is_deleted"),
        Index("idx_files_source_folder_id", "source_folder_id"),
        Index("idx_files_hash", "file_hash"),
        Index("idx_files_modified_at", "file_modified_at"),
    )
