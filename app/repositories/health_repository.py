"""Infrastructure checks used by the system health endpoint."""

from sqlalchemy import text

from app.database.connection import engine


class HealthRepository:
    """Check availability of required infrastructure dependencies."""

    def is_database_available(self) -> bool:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
