"""Text extraction from PDF documents; OCR is intentionally unsupported."""

from pathlib import Path

from pypdf import PdfReader


def extract_pdf_text(file_path: str | Path) -> str:
    """Extract text from each readable PDF page."""
    reader = PdfReader(str(file_path), strict=False)
    return "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()
