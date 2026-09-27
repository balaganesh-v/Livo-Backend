"""Application service for readiness checks."""

from sqlalchemy.exc import SQLAlchemyError

from app.repositories.health_repository import HealthRepository


class HealthService:
    def __init__(self, repository: HealthRepository | None = None) -> None:
        self.repository = repository or HealthRepository()

    def is_ready(self) -> bool:
        try:
            return self.repository.is_database_available()
        except SQLAlchemyError:
            return False
