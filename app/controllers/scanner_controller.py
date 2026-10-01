import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.file_scan import FileScanRequest, FileScanResponse
from app.services.scan_service import ScanService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scans", tags=["scans"])

scan_service = ScanService()


@router.post("", response_model=FileScanResponse)
def scan_files(request: FileScanRequest) -> FileScanResponse:
    """Run a scan and return its persisted summary."""
    try:
        result = scan_service.scan(request.folder_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Selected folder does not exist") from exc
    except NotADirectoryError as exc:
        raise HTTPException(status_code=400, detail="Selected path is not a directory") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="Selected folder cannot be accessed") from exc
    except OSError as exc:
        logger.exception("Folder scan failed")
        raise HTTPException(status_code=500, detail="Folder scan failed") from exc
    except SQLAlchemyError as exc:
        logger.exception("Database operation failed during scan")
        raise HTTPException(status_code=500, detail="Scan persistence failed") from exc
    except Exception as exc:
        # Keep unexpected failures observable in the server logs while returning
        # a useful, stable response instead of FastAPI's plain-text 500 page.
        logger.exception("Unexpected error while scanning %s", request.folder_path)
        raise HTTPException(
            status_code=500,
            detail="Scan failed unexpectedly; check the backend logs for the cause",
        ) from exc

    return FileScanResponse(**result)
