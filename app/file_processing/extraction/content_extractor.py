"""Bounded, read-only extraction for the file formats supported by v1."""

import csv
from html.parser import HTMLParser
import io
import json
import stat
import zipfile
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from app.database.config import settings

MAX_FILE_BYTES = settings.file_content_max_bytes
MAX_EXTRACTED_CHARS = settings.file_content_max_chars
EXTRACTOR_NAME = "file-content-v1"
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024

TextExtractor = Callable[[Path, str], str]
PathExtractor = Callable[[Path], str]


class BoundedText(str):
    """Extracted string that remembers whether the configured cap cut it."""

    truncated: bool

    def __new__(cls, value: str, truncated: bool = False):
        instance = super().__new__(cls, value)
        instance.truncated = truncated
        return instance


class ContentExtractionError(Exception):
    """A safe, user-facing description of an expected extraction failure."""


def _plain_text(_file_path: Path, file_contents: str) -> str:
    return file_contents


class _MeaningfulHTMLText(HTMLParser):
    """Collect visible HTML text while excluding executable/style content."""

    _ignored_elements = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._ignored_elements:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._ignored_elements and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data.strip())


def _html_text(_file_path: Path, file_contents: str) -> str:
    parser = _MeaningfulHTMLText()
    parser.feed(file_contents)
    parser.close()
    return "\n".join(parser.parts)


def _csv_text(_file_path: Path, file_contents: str) -> str:
    rows = csv.reader(io.StringIO(file_contents, newline=""), strict=True)
    rows = iter(rows)
    headers = next(rows, None)
    if headers is None:
        return ""

    def readable_rows() -> Iterable[str]:
        yield "Headers: " + " | ".join(headers)
        for row_number, row in enumerate(rows, start=1):
            if headers and len(headers) == len(row):
                yield f"Row {row_number}: " + " | ".join(
                    f"{header}: {value}" for header, value in zip(headers, row)
                )
            else:
                yield f"Row {row_number}: " + " | ".join(row)

    return _join_bounded(readable_rows())


def _json_text(_file_path: Path, file_contents: str) -> str:
    return json.dumps(json.loads(file_contents), ensure_ascii=False, indent=2)


def _xml_text(_file_path: Path, file_contents: str) -> str:
    # Parse with entity expansion and external resource access disabled, then
    # preserve the user's original source for later analysis.
    from defusedxml import ElementTree

    ElementTree.fromstring(file_contents)
    return file_contents


def _pdf_text(file_path: Path) -> str:
    from pypdf import PdfReader

    document = PdfReader(str(file_path), strict=True)
    has_selectable_text = False

    def pages() -> Iterable[str]:
        nonlocal has_selectable_text
        for page_number, page in enumerate(document.pages, start=1):
            page_text = page.extract_text() or ""
            if page_text.strip():
                has_selectable_text = True
                yield f"[Page {page_number}]\n{page_text}"

    page_text = _join_bounded(pages())
    return page_text if has_selectable_text else ""


def _docx_text(file_path: Path) -> str:
    from docx import Document

    document = Document(file_path)
    def chunks() -> Iterable[str]:
        for item in document.iter_inner_content():
            if hasattr(item, "text"):
                if item.text:
                    yield item.text
            else:
                for row in item.rows:
                    yield " | ".join(cell.text for cell in row.cells)

    return _join_bounded(chunks())


def _xlsx_text(file_path: Path) -> str:
    from openpyxl import load_workbook

    workbook = load_workbook(file_path, read_only=True, data_only=True)
    try:
        def chunks() -> Iterable[str]:
            for sheet in workbook.worksheets:
                yield f"[Sheet: {sheet.title}]"
                for row_number, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                    values = ["" if value is None else str(value) for value in row]
                    label = "Headers" if row_number == 1 else f"Row {row_number - 1}"
                    yield f"{label}: " + " | ".join(values)

        return _join_bounded(chunks())
    finally:
        workbook.close()


def _pptx_text(file_path: Path) -> str:
    from pptx import Presentation

    presentation = Presentation(file_path)

    def chunks() -> Iterable[str]:
        for slide_number, presentation_slide in enumerate(
            presentation.slides, start=1
        ):
            title_shape = presentation_slide.shapes.title
            title = title_shape.text.strip() if title_shape and title_shape.text else ""
            yield f"[Slide {slide_number}{': ' + title if title else ''}]"
            for slide_shape in presentation_slide.shapes:
                if title_shape and slide_shape.shape_id == title_shape.shape_id:
                    continue
                if slide_shape.has_text_frame and slide_shape.text:
                    yield slide_shape.text
                if slide_shape.has_table:
                    for table_row in slide_shape.table.rows:
                        yield " | ".join(
                            table_cell.text for table_cell in table_row.cells
                        )

    return _join_bounded(chunks())


# A central extension registry keeps the service independent of format details.
TEXT_EXTRACTORS: dict[str, TextExtractor] = {
    **{extension: _plain_text for extension in (
        ".txt", ".md", ".log", ".ini", ".cfg", ".conf",
        ".yaml", ".yml", ".py", ".js", ".ts", ".tsx", ".css", ".sql",
    )},
    ".html": _html_text,
    ".htm": _html_text,
    ".csv": _csv_text,
    ".json": _json_text,
    ".xml": _xml_text,
}
DOCUMENT_EXTRACTORS: dict[str, PathExtractor] = {
    ".pdf": _pdf_text,
    ".docx": _docx_text,
    ".xlsx": _xlsx_text,
    ".pptx": _pptx_text,
}
SUPPORTED_EXTENSIONS = set(TEXT_EXTRACTORS) | set(DOCUMENT_EXTRACTORS)


def extract_file_content(file_path: str | Path) -> dict[str, Any]:
    """Extract a supported file without executing it or changing the original."""
    resolved_file_path = Path(file_path)
    file_extension = resolved_file_path.suffix.lower()
    if file_extension not in SUPPORTED_EXTENSIONS:
        return _build_extraction_result("unsupported")

    try:
        _validate_file(resolved_file_path)
        if file_extension in DOCUMENT_EXTRACTORS:
            if file_extension in {".docx", ".xlsx", ".pptx"}:
                _validate_archive_expansion(resolved_file_path)
            extracted_text = DOCUMENT_EXTRACTORS[file_extension](resolved_file_path)
        else:
            file_bytes = _read_bounded(resolved_file_path)
            file_contents = file_bytes.decode("utf-8-sig")
            extracted_text = TEXT_EXTRACTORS[file_extension](
                resolved_file_path, file_contents
            )
        truncated = bool(getattr(extracted_text, "truncated", False))
        if len(extracted_text) > MAX_EXTRACTED_CHARS:
            truncated = True
        extracted_text = extracted_text[:MAX_EXTRACTED_CHARS]
        if file_extension == ".pdf" and not extracted_text.strip():
            return _build_extraction_result(
                "requires_ocr",
                "",
                "No selectable text was found; OCR is required for this PDF.",
            )
        extraction_status = (
            "truncated" if truncated else "completed" if extracted_text.strip() else "empty"
        )
        message = (
            f"Extracted text was truncated at the configured {MAX_EXTRACTED_CHARS}-character limit."
            if truncated
            else None
        )
        return _build_extraction_result(extraction_status, extracted_text, message)
    except ContentExtractionError as exc:
        return _build_extraction_result("failed", error=str(exc))
    except FileNotFoundError:
        return _build_extraction_result("failed", error="File does not exist.")
    except PermissionError:
        return _build_extraction_result("failed", error="File cannot be accessed.")
    except UnicodeDecodeError:
        return _build_extraction_result(
            "failed", error="File is not valid UTF-8 text."
        )
    except Exception:
        # Format parser exceptions can include paths, document content, or
        # implementation details. Keep the persisted error deliberately broad.
        return _build_extraction_result(
            "failed", error="File content could not be extracted."
        )


def validate_file_path(file_path: str | Path, source_root: str | Path) -> Path:
    """Ensure the stored path is a regular, non-symlink file inside its root."""
    path = Path(file_path)
    root = Path(source_root)
    try:
        absolute_path = path.absolute()
        absolute_root = root.absolute()
        try:
            relative = absolute_path.relative_to(absolute_root)
        except ValueError as exc:
            raise ContentExtractionError(
                "File is outside its authorized source folder."
            ) from exc
        cursor = absolute_root
        for part in relative.parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise ContentExtractionError("Symbolic links are not supported.")
        resolved_root = root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        if not resolved_root.is_dir() or not resolved_path.is_relative_to(resolved_root):
            raise ContentExtractionError("File is outside its authorized source folder.")
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ContentExtractionError("The target is not a regular file.")
        if path.lstat().st_size > MAX_FILE_BYTES:
            raise ContentExtractionError(_size_limit_message())
        return path
    except ContentExtractionError:
        raise
    except FileNotFoundError as exc:
        raise ContentExtractionError("File does not exist.") from exc
    except PermissionError as exc:
        raise ContentExtractionError("File cannot be accessed.") from exc
    except OSError as exc:
        raise ContentExtractionError("File path could not be validated.") from exc


def _validate_file(path: Path) -> None:
    if path.is_symlink():
        raise ContentExtractionError("Symbolic links are not supported.")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise ContentExtractionError("The target is not a regular file.")
    if info.st_size > MAX_FILE_BYTES:
        raise ContentExtractionError(_size_limit_message())


def _read_bounded(path: Path) -> bytes:
    with path.open("rb") as source:
        content = source.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise ContentExtractionError(_size_limit_message())
    return content


def _validate_archive_expansion(path: Path) -> None:
    """Reject document archives whose declared expanded size is excessive."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > 10_000:
                raise ContentExtractionError("Document contains too many archive entries.")
            if sum(info.file_size for info in infos) > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise ContentExtractionError("Document archive exceeds the expanded-size limit.")
    except zipfile.BadZipFile as exc:
        raise ContentExtractionError("Document archive is invalid.") from exc


def _join_bounded(chunks: Iterable[str]) -> BoundedText:
    parts: list[str] = []
    count = 0
    truncated = False
    for chunk in chunks:
        if count >= MAX_EXTRACTED_CHARS:
            if chunk:
                truncated = True
            break
        remaining = MAX_EXTRACTED_CHARS - count
        piece = chunk[:remaining]
        parts.append(piece)
        count += len(piece)
        if len(piece) < len(chunk):
            truncated = True
            break
    joined = "\n".join(parts)
    if len(joined) > MAX_EXTRACTED_CHARS:
        truncated = True
    return BoundedText(joined[:MAX_EXTRACTED_CHARS], truncated)


def _size_limit_message() -> str:
    return f"File exceeds the configured {MAX_FILE_BYTES}-byte extraction limit."


def _build_extraction_result(
    status: str, text: str | None = None, error: str | None = None
) -> dict[str, Any]:
    return {
        "extraction_status": status,
        "extracted_text": text,
        "character_count": len(text or ""),
        "extractor_name": EXTRACTOR_NAME,
        "error": error,
    }
