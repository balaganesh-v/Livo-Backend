"""Text extraction from DOCX paragraphs and tables."""

from pathlib import Path

from docx import Document


def extract_docx_text(file_path: str | Path) -> str:
    """Extract paragraphs and table cells while retaining section breaks."""
    document = Document(str(file_path))
    sections = [paragraph.text for paragraph in document.paragraphs if paragraph.text]
    for table in document.tables:
        rows = ["\t".join(cell.text for cell in row.cells) for row in table.rows]
        if rows:
            sections.append("\n".join(rows))
    return "\n\n".join(sections)
