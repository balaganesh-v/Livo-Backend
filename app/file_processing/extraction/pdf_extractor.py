"""Bounded PDF text extraction without OCR."""

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_PDF_BYTES = 100 * 1024 * 1024
MAX_PDF_TEXT_CHARS = 200_000


def extract_pdf_file(
    file_path: str | Path,
    max_bytes: int = MAX_PDF_BYTES,
    max_chars: int = MAX_PDF_TEXT_CHARS,
) -> dict[str, object]:
    """Extract bounded page text from PDFs up to 100 MB."""
    try:
        path = Path(file_path)
        if path.stat().st_size > max_bytes:
            return _failure(f"PDF exceeds the {max_bytes // (1024 * 1024)} MB extraction limit", truncated=True)
        if max_chars <= 0:
            raise ValueError("max_chars must be positive")

        with path.open("rb") as stream:
            reader = PdfReader(stream, strict=False)
            if reader.is_encrypted:
                return _failure("This PDF is encrypted and cannot be analyzed")

            pieces: list[str] = []
            chars_read = 0
            truncated = False
            for page in reader.pages:
                page_text = page.extract_text() or ""
                remaining = max_chars - chars_read
                if len(page_text) > remaining:
                    pieces.append(page_text[:remaining])
                    truncated = True
                    break
                pieces.append(page_text)
                chars_read += len(page_text)

        content = "\n".join(pieces).strip()
        if not content:
            return {
                "success": True,
                "content": "",
                "content_length": 0,
                "truncated": truncated,
                "error": (
                    "This PDF contains no extractable text. It may be a scanned document; "
                    "OCR is not enabled, so convert it to a searchable PDF or provide a text-based PDF."
                ),
            }
        return {
            "success": True,
            "content": content,
            "content_length": len(content),
            "truncated": truncated,
            "error": None,
        }
    except PdfReadError:
        return _failure("This PDF is damaged or has an unsupported format")
    except Exception:
        return _failure("Could not read this PDF. It may be damaged or use unsupported features")


def _failure(error: str, *, truncated: bool = False) -> dict[str, object]:
    return {
        "success": False,
        "content": None,
        "content_length": 0,
        "truncated": truncated,
        "error": error,
    }
