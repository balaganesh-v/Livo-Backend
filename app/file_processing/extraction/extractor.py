"""File type classification and dispatch to safe content extractors."""

import mimetypes
from pathlib import Path

from app.file_processing.extraction.docx_extractor import extract_docx_file
from app.file_processing.extraction.pdf_extractor import extract_pdf_file
from app.file_processing.extraction.text_extractor import extract_text_file

TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".xml", ".log"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z", ".tar", ".gz"}
EXECUTABLE_EXTENSIONS = {".exe", ".msi"}
TEXT_MIME_PREFIXES = ("text/",)
IMAGE_MIME_PREFIXES = ("image/",)


def detect_file_type(file_path: str | Path, mime_type: str | None = None) -> str:
    """Classify by explicit known extension, falling back to MIME type."""
    path = Path(file_path)
    extension = path.suffix.lower()
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

    detected_mime = mime_type or mimetypes.guess_type(path.name)[0]
    if detected_mime == "application/pdf":
        return "pdf"
    if detected_mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return "docx"
    if detected_mime and detected_mime.startswith(TEXT_MIME_PREFIXES):
        return "text"
    if detected_mime and detected_mime.startswith(IMAGE_MIME_PREFIXES):
        return "image"
    if detected_mime in {
        "application/zip",
        "application/x-rar-compressed",
        "application/vnd.rar",
        "application/x-7z-compressed",
        "application/x-tar",
        "application/gzip",
        "application/x-gzip",
    }:
        return "archive"
    if detected_mime in {"application/x-msdownload", "application/x-msi"}:
        return "executable"
    return "unknown"


def extract_file_content(file_path: str | Path) -> dict[str, object]:
    """Classify and safely extract supported content from a filesystem path."""
    path = Path(file_path).expanduser()
    file_type = detect_file_type(path)
    base: dict[str, object] = {
        "file_path": str(path),
        "file_type": file_type,
        "supported": file_type in {"text", "pdf", "docx"},
    }
    try:
        if not path.exists() or not path.is_file():
            raise FileNotFoundError("File does not exist or is not a regular file")
        if file_type == "text":
            result = extract_text_file(path)
        elif file_type == "pdf":
            result = extract_pdf_file(path)
        elif file_type == "docx":
            result = extract_docx_file(path)
        else:
            result = {
                "success": True,
                "content": None,
                "content_length": 0,
                "truncated": False,
                "error": None,
            }
    except OSError as exc:
        result = {
            "success": False,
            "content": None,
            "content_length": 0,
            "truncated": False,
            "error": f"Could not read file: {exc}",
        }
    return {**base, **result}
