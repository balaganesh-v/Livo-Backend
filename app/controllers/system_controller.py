from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.services.health_service import HealthService

router = APIRouter(tags=["system"])


def get_health_service() -> HealthService:
    """Dependency hook that can be overridden in API-level tests."""
    return HealthService()


@router.get("/")
def root() -> dict[str, str]:
    return {"message": "AI Folder Organizer API is running"}


@router.get("/health")
def health_check(
    service: Annotated[HealthService, Depends(get_health_service)],
) -> dict[str, str]:
    """Return readiness only when the database is reachable."""
    if not service.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        )
    return {"status": "ok"}
