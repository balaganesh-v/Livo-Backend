from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base


class OrganizationWorkflow(Base):
    __tablename__ = "organization_workflows"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    source_folder_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), ForeignKey("source_folders.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    stage: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extraction_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    categorization_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    review_files: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    plan_id: Mapped[int | None] = mapped_column(BIGINT(unsigned=True), ForeignKey("organization_plans.id", ondelete="SET NULL"), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"))
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP"), server_onupdate=text("CURRENT_TIMESTAMP"))

    __table_args__ = (
        UniqueConstraint("user_id", "source_folder_id", name="uq_ow_user_source"),
        Index("idx_ow_user_status", "user_id", "status"),
        Index("idx_ow_source_folder", "source_folder_id"),
    )
