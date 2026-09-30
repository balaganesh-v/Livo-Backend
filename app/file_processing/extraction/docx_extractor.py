"""DOCX text extraction."""

from io import BytesIO
from pathlib import Path

from docx import Document

from app.file_processing.extraction.text_extractor import MAX_TEXT_EXTRACTION_BYTES


def extract_docx_file(
    file_path: str | Path,
    max_bytes: int = MAX_TEXT_EXTRACTION_BYTES,
) -> dict[str, object]:
    """Extract paragraph text from a DOCX within a bounded input size."""
    try:
        with Path(file_path).open("rb") as stream:
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            return _failure("DOCX exceeds the maximum extraction size", truncated=True)
        document = Document(BytesIO(data))
        content = "\n".join(p.text for p in document.paragraphs).strip()
        return {
            "success": True,
            "content": content,
            "content_length": len(content),
            "truncated": False,
            "error": None if content else "No extractable text found in DOCX",
        }
    except Exception as exc:
        return _failure(f"Could not extract DOCX content: {exc}")


def _failure(error: str, *, truncated: bool = False) -> dict[str, object]:
    return {
        "success": False,
        "content": None,
        "content_length": 0,
        "truncated": truncated,
        "error": error,
    }
