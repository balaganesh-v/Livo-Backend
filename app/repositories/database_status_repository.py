
from sqlalchemy import text

from app.database.connection import engine


class DatabaseStatusRepository:
    def is_database_available(self) -> bool:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return True
