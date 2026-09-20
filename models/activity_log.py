from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class ActivityStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"


class ActivityLog(Base):
    __tablename__ = "activity_logs"

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

    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    entity_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    entity_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        nullable=True,
    )

    file_id: Mapped[int | None] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("files.id", ondelete="SET NULL"),
        nullable=True,
    )

    details: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    status: Mapped[ActivityStatus] = mapped_column(
        SAEnum(ActivityStatus),
        nullable=False,
        default=ActivityStatus.SUCCESS,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )

    performed_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    user = relationship(
        "User",
        back_populates="activity_logs",
    )

    file = relationship(
        "File",
        back_populates="activity_logs",
    )

    __table_args__ = (
        Index(
            "idx_al_user_performed",
            "user_id",
            "performed_at",
        ),
        Index("idx_al_action", "action"),
        Index(
            "idx_al_entity",
            "entity_type",
            "entity_id",
        ),
    )
