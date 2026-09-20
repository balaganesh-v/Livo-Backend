from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.mysql import BIGINT, LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class DocumentSummary(Base):
    __tablename__ = "document_summaries"

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

    summary_text: Mapped[str] = mapped_column(
        LONGTEXT,
        nullable=False,
    )

    word_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    model_used: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    generated_at: Mapped[datetime] = mapped_column(
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

    file = relationship(
        "File",
        back_populates="document_summary",
    )
