from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.base import Base


class SourceFolderStatus(str, Enum):
    ACTIVE = "active"
    SCANNING = "scanning"
    COMPLETED = "completed"
    FAILED = "failed"
    DISABLED = "disabled"


class SourceFolder(Base):
    __tablename__ = "source_folders"

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

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    folder_path: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    status: Mapped[SourceFolderStatus] = mapped_column(
        SAEnum(SourceFolderStatus),
        nullable=False,
        default=SourceFolderStatus.ACTIVE,
    )

    last_scanned_at: Mapped[datetime | None] = mapped_column(
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
        back_populates="source_folders",
    )

    scan_jobs = relationship(
        "ScanJob",
        back_populates="source_folder",
        cascade="all, delete-orphan",
    )

    files = relationship(
        "File",
        back_populates="source_folder",
        cascade="all, delete-orphan",
    )

    organization_plans = relationship(
        "OrganizationPlan",
        back_populates="source_folder",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_sf_user_id", "user_id"),
        Index("idx_sf_status", "status"),
        Index(
            "uq_sf_user_path",
            "user_id",
            "folder_path",
            unique=True,
            mysql_length={"folder_path": 500},
        ),
    )
