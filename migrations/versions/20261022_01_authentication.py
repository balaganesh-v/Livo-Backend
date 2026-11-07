"""Add usernames and persisted refresh sessions for authentication."""

from alembic import op
from sqlalchemy import (Column, DateTime, ForeignKeyConstraint, String,
                        inspect, text)
from sqlalchemy.dialects.mysql import BIGINT

revision = "20261022_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create current model tables, then migrate existing users safely."""
    bind = op.get_bind()
    from app import models  # noqa: F401
    from app.database.base import Base

    Base.metadata.create_all(bind=bind)
    database_inspector = inspect(bind)
    user_columns = {
        column["name"] for column in database_inspector.get_columns("users")
    }
    if "username" not in user_columns:
        op.add_column(
            "users",
            Column("username", String(50), nullable=True),
        )
    existing_user_indexes = {
        index["name"] for index in inspect(bind).get_indexes("users")
    }
    if "uq_users_username" not in existing_user_indexes:
        op.create_index("uq_users_username", "users", ["username"], unique=True)

    if "refresh_sessions" not in inspect(bind).get_table_names():
        op.create_table(
            "refresh_sessions",
            Column(
                "id",
                BIGINT(unsigned=True),
                primary_key=True,
                autoincrement=True,
                nullable=False,
            ),
            Column("user_id", BIGINT(unsigned=True), nullable=False),
            Column("token_hash", String(64), nullable=False, unique=True),
            Column("expires_at", DateTime(), nullable=False),
            Column("revoked_at", DateTime(), nullable=True),
            Column(
                "created_at",
                DateTime(),
                nullable=False,
                server_default=text("CURRENT_TIMESTAMP"),
            ),
            ForeignKeyConstraint(
                ["user_id"],
                ["users.id"],
                ondelete="CASCADE",
                name="fk_refresh_user",
            ),
        )
        op.create_index(
            "ix_refresh_sessions_user_expiry",
            "refresh_sessions",
            ["user_id", "expires_at"],
        )


def downgrade() -> None:
    """Remove auth-only schema additions without changing existing user rows."""
    bind = op.get_bind()
    database_inspector = inspect(bind)
    if "refresh_sessions" in database_inspector.get_table_names():
        op.drop_table("refresh_sessions")

    if "users" in inspect(bind).get_table_names():
        existing_user_indexes = {
            index["name"] for index in inspect(bind).get_indexes("users")
        }
        if "uq_users_username" in existing_user_indexes:
            op.drop_index("uq_users_username", table_name="users")
        user_columns = {
            column["name"] for column in inspect(bind).get_columns("users")
        }
        if "username" in user_columns:
            op.drop_column("users", "username")
