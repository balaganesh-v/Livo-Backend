from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.base import Base


class DuplicateFile(Base):
    __tablename__ = "duplicate_files"

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )

    duplicate_group_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("duplicate_groups.id", ondelete="CASCADE"),
        nullable=False,
    )

    file_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )

    is_recommended_keep: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    duplicate_group = relationship(
        "DuplicateGroup",
        back_populates="duplicate_files",
    )

    file = relationship(
        "File",
        back_populates="duplicate_files",
    )

    __table_args__ = (
        Index(
            "uq_df_group_file",
            "duplicate_group_id",
            "file_id",
            unique=True,
        ),
        Index("idx_df_group_id", "duplicate_group_id"),
        Index("idx_df_file_id", "file_id"),
    )
