from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class DuplicateGroup(Base):
    __tablename__ = "duplicate_groups"

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

    file_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    file_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    total_size_bytes: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        nullable=False,
        default=0,
    )

    wasted_size_bytes: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        nullable=False,
        default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    user = relationship(
        "User",
        back_populates="duplicate_groups",
    )

    duplicate_files = relationship(
        "DuplicateFile",
        back_populates="duplicate_group",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "uq_dg_user_hash",
            "user_id",
            "file_hash",
            unique=True,
        ),
        Index("idx_dg_user_id", "user_id"),
        Index("idx_dg_hash", "file_hash"),
    )
