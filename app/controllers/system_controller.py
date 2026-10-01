import logging

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.database.connection import engine

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


@router.get("/")
def root() -> dict[str, str]:
    return {"message": "AI Folder Organizer API is running"}


@router.get("/health")
def health_check() -> dict[str, str]:
    """Return readiness only when the database is reachable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.exception("Database health check failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc

    return {"status": "ok"}
