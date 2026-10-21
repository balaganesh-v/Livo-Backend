from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT as MySQLBIGINT
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.base import Base


class FileContent(Base):
    __tablename__ = "file_contents"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
    )

    file_id: Mapped[int] = mapped_column(
        MySQLBIGINT(unsigned=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    extracted_text: Mapped[str | None] = mapped_column(
        LONGTEXT,
        nullable=True,
    )

    extraction_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default=text("'pending'"),
    )

    extractor_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    extraction_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    extracted_at: Mapped[datetime | None] = mapped_column(
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
        onupdate=datetime.utcnow,
    )

    file = relationship(
        "File",
        back_populates="content",
    )

    __table_args__ = (Index("ix_file_contents_extraction_status", "extraction_status"),)

