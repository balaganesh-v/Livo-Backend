from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.base import Base


class FileAIAnalysis(Base):
    __tablename__ = "file_ai_analysis"

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )

    file_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    subcategory: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    keywords: Mapped[list | None] = mapped_column(
        JSON,
        nullable=True,
    )

    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )

    content_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    is_personal: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    is_work_related: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    is_study_related: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    model_used: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    file = relationship(
        "File",
        back_populates="ai_analysis",
    )

    __table_args__ = (Index("idx_fai_category", "category"),)
