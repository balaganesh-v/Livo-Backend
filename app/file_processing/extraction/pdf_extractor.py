"""PDF text extraction without OCR."""

from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from app.file_processing.extraction.text_extractor import MAX_TEXT_EXTRACTION_BYTES


def extract_pdf_file(
    file_path: str | Path,
    max_bytes: int = MAX_TEXT_EXTRACTION_BYTES,
) -> dict[str, object]:
    """Extract page text from a PDF, returning an error instead of raising."""
    try:
        path = Path(file_path)
        with path.open("rb") as stream:
            data = stream.read(max_bytes + 1)
        truncated = len(data) > max_bytes
        if truncated:
            return _failure("PDF exceeds the maximum extraction size", truncated=True)
        reader = PdfReader(BytesIO(data), strict=False)
        content = "\n".join(page.extract_text() or "" for page in reader.pages)
        content = content.strip()
        return {
            "success": True,
            "content": content,
            "content_length": len(content),
            "truncated": False,
            "error": None if content else "No extractable text found in PDF",
        }
    except Exception as exc:
        return _failure(f"Could not extract PDF content: {exc}")


def _failure(error: str, *, truncated: bool = False) -> dict[str, object]:
    return {
        "success": False,
        "content": None,
        "content_length": 0,
        "truncated": truncated,
        "error": error,
    }
