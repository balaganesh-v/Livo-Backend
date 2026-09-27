"""Central dispatcher for safe, read-only file content extraction."""

import logging
import mimetypes
from pathlib import Path
from typing import Any

from app.file_processing.extraction.docx_extractor import extract_docx_text
from app.file_processing.extraction.pdf_extractor import extract_pdf_text
from app.file_processing.extraction.text_extractor import extract_text
from app.file_processing.metadata.file_metadata import FileMetadata, extract_file_metadata

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml", ".log"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz"}
EXECUTABLE_EXTENSIONS = {".exe", ".msi"}


def classify_file_type(
    file_path: str | Path, metadata: FileMetadata | None = None
) -> str:
    """Classify a file using known extensions first and MIME as a fallback."""
    path = Path(file_path)
    extension = (metadata.extension if metadata else path.suffix.lower()) or ""
    if extension in TEXT_EXTENSIONS:
        return "text"
    if extension == ".pdf":
        return "pdf"
    if extension == ".docx":
        return "docx"
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in ARCHIVE_EXTENSIONS:
        return "archive"
    if extension in EXECUTABLE_EXTENSIONS:
        return "executable"

    mime_type = metadata.mime_type if metadata else mimetypes.guess_type(path.name)[0]
    if mime_type == "application/pdf":
        return "pdf"
    if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return "docx"
    if mime_type and mime_type.startswith("text/"):
        return "text"
    if mime_type and mime_type.startswith("image/"):
        return "image"
    if mime_type in {"application/zip", "application/x-tar", "application/gzip", "application/x-7z-compressed", "application/vnd.rar"}:
        return "archive"
    if mime_type in {"application/x-msdownload", "application/x-msi", "application/vnd.microsoft.portable-executable"}:
        return "executable"
    return "unknown"


def extract_content(file_path: str | Path) -> dict[str, Any]:
    """Extract supported text content and return a stable, failure-tolerant result."""
    path = Path(file_path).expanduser()
    result: dict[str, Any] = {
        "file_path": str(path),
        "file_type": "unknown",
        "supported": False,
        "success": False,
        "content": None,
        "content_length": 0,
        "truncated": False,
        "error": None,
    }
    try:
        if not path.exists():
            raise FileNotFoundError("File does not exist")
        if not path.is_file():
            raise OSError("Path is not a regular file")
        metadata = extract_file_metadata(path)
        file_type = classify_file_type(path, metadata)
        result["file_path"] = metadata.file_path
        result["file_type"] = file_type
        result["supported"] = file_type in {"text", "pdf", "docx"}
        if not result["supported"]:
            result["success"] = True
            return result

        if file_type == "text":
            content, truncated = extract_text(path)
        elif file_type == "pdf":
            content, truncated = extract_pdf_text(path), False
        else:
            content, truncated = extract_docx_text(path), False

        result.update(
            success=True,
            content=content,
            content_length=len(content),
            truncated=truncated,
        )
    except (OSError, ValueError, Exception) as exc:
        # Parser libraries raise different exception types; retain details for diagnosis.
        logger.warning("Content extraction failed for %s: %s", path, exc, exc_info=True)
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def extract_file_content(file_path: str | Path) -> dict[str, Any]:
    """Alias with an explicit name for callers in the processing pipeline."""
    return extract_content(file_path)
