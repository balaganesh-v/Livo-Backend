from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
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


class OrganizationAction(str, Enum):
    MOVE = "move"
    RENAME = "rename"
    KEEP = "keep"
    SKIP = "skip"


class OrganizationItemStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


class OrganizationPlanItem(Base):
    __tablename__ = "organization_plan_items"

    id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        primary_key=True,
        autoincrement=True,
    )

    plan_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("organization_plans.id", ondelete="CASCADE"),
        nullable=False,
    )

    file_id: Mapped[int] = mapped_column(
        BIGINT(unsigned=True),
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )

    current_path: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    proposed_path: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )

    action: Mapped[OrganizationAction] = mapped_column(
        SAEnum(OrganizationAction),
        nullable=False,
        default=OrganizationAction.MOVE,
    )

    status: Mapped[OrganizationItemStatus] = mapped_column(
        SAEnum(OrganizationItemStatus),
        nullable=False,
        default=OrganizationItemStatus.PENDING,
    )

    reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    confidence: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )

    executed_at: Mapped[datetime | None] = mapped_column(
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

    plan = relationship(
        "OrganizationPlan",
        back_populates="items",
    )

    file = relationship(
        "File",
        back_populates="organization_plan_items",
    )

    __table_args__ = (
        Index(
            "uq_opi_plan_file",
            "plan_id",
            "file_id",
            unique=True,
        ),
        Index("idx_opi_plan_id", "plan_id"),
        Index("idx_opi_file_id", "file_id"),
        Index("idx_opi_status", "status"),
    )
