
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.connection import get_database_session
from app.models.user import User
from app.schemas.scanner_schema import (
    FolderScanRequest,
    FileScanResponse,
    ScannedFileResponse,
)
from app.security.authentication import get_current_user
from app.services.scanner_service import ScannerService

router = APIRouter(prefix="/api/scans", tags=["Scans"])


@router.post("", response_model=FileScanResponse)
def scan_selected_folder(
    request: FolderScanRequest,
    session: Session = Depends(get_database_session),
    current_user: User = Depends(get_current_user),
) -> FileScanResponse:
    scanner_service = ScannerService(session)

    try:
        scan_result = scanner_service.scan_folder_and_save_file_metadata(
            request.folder_path,
            current_user.id,
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="The selected folder does not exist.",
        )
    except NotADirectoryError:
        raise HTTPException(
            status_code=400,
            detail="The selected path is not a folder.",
        )
    except PermissionError:
        raise HTTPException(
            status_code=403,
            detail="Permission denied. The selected folder cannot be accessed.",
        )
    except OSError:
        raise HTTPException(
            status_code=400,
            detail="The selected folder could not be scanned.",
        )

    scanned_files = []

    for scanned_file in scan_result.files:
        scanned_files.append(
            ScannedFileResponse(
                file_id=scanned_file.file_id,
                name=scanned_file.metadata.name,
                file_path=scanned_file.metadata.file_path,
                extension=scanned_file.metadata.extension,
                mime_type=scanned_file.metadata.mime_type,
                size_bytes=scanned_file.metadata.size_bytes,
                file_hash=scanned_file.file_hash,
                file_created_at=scanned_file.metadata.file_created_at,
                file_modified_at=scanned_file.metadata.file_modified_at,
                scanned_at=scanned_file.metadata.scanned_at,
                error=scanned_file.error,
            )
        )

    return FileScanResponse(
        folder_path=scan_result.folder_path,
        files_discovered=scan_result.total_files,
        records_persisted=scan_result.saved_files,
        total_files=scan_result.total_files,
        processed_files=scan_result.processed_files,
        saved_files=scan_result.saved_files,
        failed_files=scan_result.failed_files,
        files=scanned_files,
    )
