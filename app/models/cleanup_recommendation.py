from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.base import Base


class CleanupReason(str, Enum):
    DUPLICATE = "duplicate"
    OLD_INSTALLER = "old_installer"
    TEMPORARY_FILE = "temporary_file"
    LARGE_UNUSED = "large_unused"
    CACHE = "cache"
    USER_FLAGGED = "user_flagged"


class CleanupRecommendationType(str, Enum):
    DELETE = "delete"
    ARCHIVE = "archive"
    REVIEW = "review"
    KEEP = "keep"


class CleanupStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"


class CleanupRecommendation(Base):
    __tablename__ = "cleanup_recommendations"

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

    file_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    reason: Mapped[CleanupReason] = mapped_column(
        SAEnum(CleanupReason),
        nullable=False,
    )

    recommendation: Mapped[CleanupRecommendationType] = mapped_column(
        SAEnum(CleanupRecommendationType),
        nullable=False,
    )

    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )

    status: Mapped[CleanupStatus] = mapped_column(
        SAEnum(CleanupStatus),
        nullable=False,
        default=CleanupStatus.PENDING,
    )

    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    user = relationship(
        "User",
        back_populates="cleanup_recommendations",
    )

    file = relationship(
        "File",
        back_populates="cleanup_recommendation",
    )

    __table_args__ = (
        Index("idx_cr_user_id", "user_id"),
        Index("idx_cr_status", "status"),
    )
