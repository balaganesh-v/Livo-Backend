"""Add persisted post-scan organization workflows."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql
from sqlalchemy import inspect

revision = "20261031_01"
down_revision = "20261022_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The preceding legacy migration calls Base.metadata.create_all() and can
    # create this table from the current model registry before this revision runs.
    if "organization_workflows" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "organization_workflows",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("source_folder_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("stage", sa.String(length=30), nullable=False),
        sa.Column("total_files", sa.Integer(), nullable=False),
        sa.Column("extraction_counts", sa.JSON(), nullable=False),
        sa.Column("categorization_counts", sa.JSON(), nullable=False),
        sa.Column("review_files", sa.JSON(), nullable=False),
        sa.Column("plan_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["organization_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_folder_id"], ["source_folders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source_folder_id", name="uq_ow_user_source"),
    )
    op.create_index("idx_ow_user_status", "organization_workflows", ["user_id", "status"])
    op.create_index("idx_ow_source_folder", "organization_workflows", ["source_folder_id"])


def downgrade() -> None:
    op.drop_index("idx_ow_source_folder", table_name="organization_workflows")
    op.drop_index("idx_ow_user_status", table_name="organization_workflows")
    op.drop_table("organization_workflows")
