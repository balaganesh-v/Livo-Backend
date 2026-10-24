
from app.repositories.database_status_repository import (
    DatabaseStatusRepository,
)


class AppService:
    def __init__(self) -> None:
        self.database_repository = DatabaseStatusRepository()

    def is_database_connected(self) -> bool:
        return self.database_repository.is_database_available()
