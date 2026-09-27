import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import models  # noqa: F401
from app.database.base import Base
from app.database.connection import engine
from app.schemas.file_scan import (
    FileScanRequest,
    FileScanResponse,
    ScannedFileResponse,
)
from app.services.file_scanner_service import FileScannerService

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Verify required infrastructure before accepting requests."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Database connection failed during startup")
        raise

    Base.metadata.create_all(bind=engine)
    print("✅ Database connection established")
    yield


app = FastAPI(
    title="AI Folder Organizer API",
    version="1.0.0",
    lifespan=lifespan,
)

scanner_service = FileScannerService()


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {"message": "AI Folder Organizer API is running"}


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Return readiness only when the database is reachable."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc

    return {"status": "ok"}


@app.post("/api/scans", response_model=FileScanResponse, tags=["scans"])
def scan_files(request: FileScanRequest) -> FileScanResponse:
    """Synchronously scan a selected folder and return file metadata and hashes."""
    try:
        result = scanner_service.scan(request.folder_path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Selected folder does not exist",
        ) from exc
    except NotADirectoryError as exc:
        raise HTTPException(
            status_code=400,
            detail="Selected path is not a directory",
        ) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Selected folder cannot be accessed") from exc
    except OSError as exc:
        logger.exception("Folder scan failed")
        raise HTTPException(status_code=500, detail="Folder scan failed") from exc

    return FileScanResponse(
        folder_path=result.folder_path,
        total_files=result.total_files,
        processed_files=result.processed_files,
        failed_files=result.failed_files,
        files=[
            ScannedFileResponse(
                **{
                    "name": item.metadata.name,
                    "file_path": item.metadata.file_path,
                    "extension": item.metadata.extension,
                    "mime_type": item.metadata.mime_type,
                    "size_bytes": item.metadata.size_bytes,
                    "file_created_at": item.metadata.file_created_at,
                    "file_modified_at": item.metadata.file_modified_at,
                    "scanned_at": item.metadata.scanned_at,
                },
                file_hash=item.file_hash,
                error=item.error,
            )
            for item in result.files
        ],
    )


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
