import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.file_scan import (
    FileScanRequest,
    FileScanResponse,
    ScannedFileResponse,
)
from app.services.scanner_service import ScannerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scans", tags=["scans"])


def get_scanner_service() -> ScannerService:
    return ScannerService()

@router.post("", response_model=FileScanResponse)
def scan_files(
    request: FileScanRequest,
    service: Annotated[ScannerService, Depends(get_scanner_service)],
) -> FileScanResponse:
    try:
        result = service.scan(request.folder_path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Selected folder does not exist",
        ) from exc
    except NotADirectoryError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected path is not a directory",
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Selected folder cannot be accessed",
        ) from exc
    except OSError as exc:
        logger.exception("Folder scan failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Folder scan failed",
        ) from exc

    return FileScanResponse(
        folder_path=result.folder_path,
        total_files=result.total_files,
        processed_files=result.processed_files,
        failed_files=result.failed_files,
        files=[
            ScannedFileResponse(
                name=item.metadata.name,
                file_path=item.metadata.file_path,
                extension=item.metadata.extension,
                mime_type=item.metadata.mime_type,
                size_bytes=item.metadata.size_bytes,
                file_hash=item.file_hash,
                file_created_at=item.metadata.file_created_at,
                file_modified_at=item.metadata.file_modified_at,
                scanned_at=item.metadata.scanned_at,
                error=item.error,
            )
            for item in result.files
        ],
    )
