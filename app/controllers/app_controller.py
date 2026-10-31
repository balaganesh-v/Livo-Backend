
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.services.app_service import AppService

router = APIRouter(prefix="/api/app", tags=["App"])


def get_app_service() -> AppService:
    return AppService()


@router.get("/")
def get_app_message() -> dict[str, str]:
    return {"message": "AI Folder Organizer API is running"}


@router.get("/status")
def get_app_status(
    app_service: Annotated[AppService, Depends(get_app_service)],
) -> dict[str, str]:
    try:
        if app_service.is_database_connected():
            return {"status": "ok"}
    except SQLAlchemyError:
        pass

    raise HTTPException(
        status_code=503,
        detail="Database connection failed",
    )
