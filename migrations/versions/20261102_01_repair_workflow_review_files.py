"""Add the review_files column to pre-existing workflow tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261102_01"
down_revision = "20261031_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("organization_workflows")}
    if "review_files" in columns:
        return

    op.add_column(
        "organization_workflows",
        sa.Column("review_files", sa.JSON(), nullable=True),
    )
    op.execute(
        sa.text("UPDATE organization_workflows SET review_files = JSON_ARRAY() WHERE review_files IS NULL")
    )
    op.alter_column(
        "organization_workflows",
        "review_files",
        existing_type=sa.JSON(),
        nullable=False,
    )


def downgrade() -> None:
    columns = {column["name"] for column in inspect(op.get_bind()).get_columns("organization_workflows")}
    if "review_files" in columns:
        op.drop_column("organization_workflows", "review_files")
