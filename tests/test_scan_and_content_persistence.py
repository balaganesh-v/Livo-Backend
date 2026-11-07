"""Persistence, extraction, and ownership tests using isolated SQLite."""

from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine, event, func, select
from sqlalchemy.dialects.mysql import BIGINT, LONGTEXT
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from docx import Document
from openpyxl import Workbook
from pptx import Presentation
from pypdf import PdfWriter

from app import models  # noqa: F401
from app.controllers import file_content_controller, scanner_controller
from app.controllers.app_controller import get_app_status
from app.database.base import Base
from app.file_processing.extraction.content_extractor import \
    SUPPORTED_EXTENSIONS
from app.file_processing.extraction import content_extractor
from app.models.file import File
from app.models.file_content import FileContent
from app.models.source_folder import SourceFolder
from app.models.user import User
from app.schemas.scanner_schema import FolderScanRequest
from app.services import file_content_service
from app.services.app_service import AppService
from app.services.file_content_service import (FileContentService,
                                               FileNotFoundInDatabaseError)
from app.services.scanner_service import ScannerService


@compiles(BigInteger, "sqlite")
def _compile_bigint_for_sqlite(type_, compiler, **kwargs):
    return "INTEGER"


@compiles(BIGINT, "sqlite")
def _compile_mysql_bigint_for_sqlite(type_, compiler, **kwargs):
    return "INTEGER"


@compiles(LONGTEXT, "sqlite")
def _compile_longtext_for_sqlite(type_, compiler, **kwargs):
    return "TEXT"


@pytest.fixture
def database_engine():
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    try:
        yield test_engine
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()


def create_test_user(session: Session, username: str) -> User:
    test_user = User(
        name=username,
        username=username,
        email=f"{username}@example.com",
        password_hash="unused-test-hash",
        is_active=True,
    )
    session.add(test_user)
    session.commit()
    return test_user


def create_text_pdf(path: Path, text: str) -> None:
    """Write a tiny real PDF page with selectable Helvetica text."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{object_number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010} 00000 n \n".encode())
    pdf.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    path.write_bytes(pdf)


def create_supported_format_samples(folder: Path) -> dict[str, str]:
    """Create original files containing recognizable, format-valid content."""
    expected: dict[str, str] = {}
    raw_text_formats = {
        ".txt", ".md", ".log", ".ini", ".cfg", ".conf", ".yaml", ".yml",
        ".py", ".js", ".ts", ".tsx", ".css", ".sql",
    }
    for extension in raw_text_formats:
        marker = f"recognizable {extension} content"
        (folder / f"sample{extension}").write_text(marker, encoding="utf-8")
        expected[extension] = marker

    (folder / "sample.csv").write_text(
        "Name,Value\nLivo,recognizable csv cell\n", encoding="utf-8"
    )
    expected[".csv"] = "recognizable csv cell"
    (folder / "sample.json").write_text(
        '{"message":"recognizable json value","items":[1,2]}', encoding="utf-8"
    )
    expected[".json"] = "recognizable json value"
    (folder / "sample.xml").write_text(
        "<root><message>recognizable xml text</message></root>", encoding="utf-8"
    )
    expected[".xml"] = "recognizable xml text"
    for extension in (".html", ".htm"):
        (folder / f"sample{extension}").write_text(
            "<html><script>hidden text</script><h1>Recognizable heading</h1>"
            "<p>recognizable html paragraph</p></html>", encoding="utf-8"
        )
        expected[extension] = "recognizable html paragraph"

    create_text_pdf(folder / "sample.pdf", "recognizable PDF text")
    expected[".pdf"] = "recognizable PDF text"

    word = Document()
    word.add_heading("Recognizable DOCX heading", level=1)
    word.add_paragraph("recognizable DOCX paragraph")
    word.add_table(rows=1, cols=1).cell(0, 0).text = "recognizable DOCX table"
    word.save(folder / "sample.docx")
    expected[".docx"] = "recognizable DOCX paragraph"

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Recognizable Sheet"
    worksheet.append(["Column", "Value"])
    worksheet.append(["Row", "recognizable XLSX cell"])
    workbook.save(folder / "sample.xlsx")
    expected[".xlsx"] = "recognizable XLSX cell"

    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "Recognizable PPTX title"
    slide.placeholders[1].text = "recognizable PPTX body"
    deck.save(folder / "sample.pptx")
    expected[".pptx"] = "recognizable PPTX body"
    return expected


def test_scan_and_extraction_persist_for_owner_and_retrieve_in_new_session(
    database_engine, tmp_path: Path
):
    scan_root = tmp_path / "picked-folder"
    scan_root.mkdir()
    (scan_root / "notes.txt").write_text("keep this text", encoding="utf-8")
    (scan_root / "broken.json").write_text("{", encoding="utf-8")
    (scan_root / "archive.zip").write_bytes(b"not extracted")

    with Session(database_engine) as database_session:
        owner = create_test_user(database_session, "test-owner")
        owner_id = owner.id
        first_scan = ScannerService(database_session).scan_folder_and_save_file_metadata(
            scan_root, owner_id
        )
        second_scan = ScannerService(database_session).scan_folder_and_save_file_metadata(
            scan_root, owner_id
        )
        assert first_scan.source_folder_id == second_scan.source_folder_id
        assert first_scan.total_files == 3
        assert first_scan.saved_files == 3
        assert second_scan.saved_files == 3
        assert database_session.scalar(select(func.count()).select_from(File)) == 3
        assert database_session.scalar(
            select(func.count()).select_from(SourceFolder)
        ) == 1
        file_ids_by_name = {
            file_record.name: file_record.id
            for file_record in database_session.scalars(select(File))
        }

        content_service = FileContentService(database_session)
        assert content_service.extract_content_for_scanned_file(
            file_ids_by_name["notes.txt"], owner_id
        ).extraction_status == "completed"
        (scan_root / "notes.txt").write_text("updated text", encoding="utf-8")
        assert content_service.extract_content_for_scanned_file(
            file_ids_by_name["notes.txt"], owner_id
        ).extraction_status == "completed"
        assert content_service.extract_content_for_scanned_file(
            file_ids_by_name["broken.json"], owner_id
        ).extraction_status == "failed"
        assert content_service.extract_content_for_scanned_file(
            file_ids_by_name["archive.zip"], owner_id
        ).extraction_status == "unsupported"

    with Session(database_engine) as verification_session:
        saved_content_records = list(
            verification_session.scalars(select(FileContent))
        )
        assert len(saved_content_records) == 3
        content_by_file_id = {
            content_record.file_id: content_record
            for content_record in saved_content_records
        }
        saved_text = content_by_file_id[file_ids_by_name["notes.txt"]]
        assert saved_text.extracted_text == "updated text"
        assert saved_text.extraction_status == "completed"
        assert saved_text.extractor_name
        assert saved_text.extracted_at is not None
        assert content_by_file_id[file_ids_by_name["broken.json"]].extraction_error
        assert (
            content_by_file_id[file_ids_by_name["archive.zip"]].extraction_status
            == "unsupported"
        )
        assert verification_session.scalar(
            select(func.count()).select_from(FileContent).where(
                FileContent.file_id == saved_text.file_id
            )
        ) == 1
        retrieved_content = FileContentService(
            verification_session
        ).get_extracted_content(saved_text.file_id, owner_id)
        assert retrieved_content.extracted_text == "updated text"


def test_scan_request_does_not_accept_client_selected_owner():
    folder_scan_request = FolderScanRequest(folder_path="C:/data")
    assert folder_scan_request.folder_path == "C:/data"
    assert "user_id" not in FolderScanRequest.model_fields


def test_extractor_registers_every_configured_format():
    assert SUPPORTED_EXTENSIONS == {
        ".txt", ".md", ".csv", ".json", ".log", ".xml", ".html", ".htm",
        ".yaml", ".yml", ".ini", ".cfg", ".conf", ".py", ".js", ".ts",
        ".tsx", ".css", ".sql", ".pdf", ".docx", ".xlsx", ".pptx",
    }


def test_real_supported_format_contents_are_returned_and_persisted(
    database_engine, tmp_path: Path
):
    expected_by_extension = create_supported_format_samples(tmp_path)
    assert set(expected_by_extension) == SUPPORTED_EXTENSIONS

    with Session(database_engine) as database_session:
        owner = create_test_user(database_session, "format-owner")
        scan_result = ScannerService(database_session).scan_folder_and_save_file_metadata(
            tmp_path, owner.id
        )
        file_ids_by_extension = {
            Path(scanned_file.metadata.file_path).suffix.lower(): scanned_file.file_id
            for scanned_file in scan_result.files
        }

        for extension, marker in expected_by_extension.items():
            file_id = file_ids_by_extension[extension]
            response = file_content_controller.extract_content_for_file(
                file_id, database_session, owner
            )
            assert marker in (response.extracted_text or ""), extension
            assert response.file_extension == extension
            saved = database_session.scalar(
                select(FileContent).where(FileContent.file_id == file_id)
            )
            assert saved is not None
            assert saved.extracted_text == response.extracted_text
            assert saved.extraction_status == "completed"
            if extension in {".html", ".htm"}:
                assert "Recognizable heading" in response.extracted_text
                assert "hidden text" not in response.extracted_text
            elif extension == ".pdf":
                assert "[Page 1]" in response.extracted_text
            elif extension == ".docx":
                text = response.extracted_text
                assert text.index("Recognizable DOCX heading") < text.index(
                    "recognizable DOCX paragraph"
                ) < text.index("recognizable DOCX table")
            elif extension == ".xlsx":
                assert "[Sheet: Recognizable Sheet]" in response.extracted_text
                assert "Headers: Column | Value" in response.extracted_text
            elif extension == ".pptx":
                assert "[Slide 1: Recognizable PPTX title]" in response.extracted_text


def test_empty_unsupported_and_truncated_results_are_explicit(
    database_engine, tmp_path: Path, monkeypatch
):
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    (tmp_path / "unsupported.bin").write_bytes(b"bytes")
    (tmp_path / "long.txt").write_text("0123456789", encoding="utf-8")
    blank_pdf = PdfWriter()
    blank_pdf.add_blank_page(width=612, height=792)
    with (tmp_path / "image-only.pdf").open("wb") as pdf_file:
        blank_pdf.write(pdf_file)

    with Session(database_engine) as database_session:
        owner = create_test_user(database_session, "status-owner")
        scan_result = ScannerService(database_session).scan_folder_and_save_file_metadata(
            tmp_path, owner.id
        )
        file_ids_by_name = {
            scanned_file.metadata.name: scanned_file.file_id
            for scanned_file in scan_result.files
        }
        empty_response = file_content_controller.extract_content_for_file(
            file_ids_by_name["empty.txt"], database_session, owner
        )
        assert empty_response.extraction_status == "empty"
        assert empty_response.extracted_text == ""
        ocr_response = file_content_controller.extract_content_for_file(
            file_ids_by_name["image-only.pdf"], database_session, owner
        )
        assert ocr_response.extraction_status == "requires_ocr"
        assert ocr_response.extracted_text == ""
        assert "OCR" in (ocr_response.error or "")
        unsupported_response = file_content_controller.extract_content_for_file(
            file_ids_by_name["unsupported.bin"], database_session, owner
        )
        assert unsupported_response.extraction_status == "unsupported"
        assert unsupported_response.failures == 1

        monkeypatch.setattr(content_extractor, "MAX_EXTRACTED_CHARS", 5)
        truncated_response = file_content_controller.extract_content_for_file(
            file_ids_by_name["long.txt"], database_session, owner
        )
        assert truncated_response.extraction_status == "truncated"
        assert truncated_response.truncated is True
        assert truncated_response.extracted_text == "01234"
        assert truncated_response.message
        saved = database_session.scalar(
            select(FileContent).where(
                FileContent.file_id == file_ids_by_name["long.txt"]
            )
        )
        assert saved.extracted_text == truncated_response.extracted_text


def test_extraction_database_failure_rolls_back_without_false_success(
    database_engine, tmp_path: Path
):
    (tmp_path / "notes.txt").write_text("database marker", encoding="utf-8")
    with Session(database_engine) as database_session:
        owner = create_test_user(database_session, "content-transaction-owner")
        scan_result = ScannerService(database_session).scan_folder_and_save_file_metadata(
            tmp_path, owner.id
        )
        file_id = scan_result.files[0].file_id

        def reject_commit(_database_session):
            raise SQLAlchemyError("simulated content commit failure")

        event.listen(database_session, "before_commit", reject_commit)
        try:
            with pytest.raises(SQLAlchemyError, match="simulated content commit failure"):
                FileContentService(database_session).extract_content_for_scanned_file(
                    file_id, owner.id
                )
        finally:
            event.remove(database_session, "before_commit", reject_commit)

    with Session(database_engine) as verification_session:
        assert verification_session.scalar(
            select(func.count()).select_from(FileContent).where(
                FileContent.file_id == file_id
            )
        ) == 0


def test_scan_database_failure_rolls_back_file_and_folder_records(
    database_engine, tmp_path: Path
):
    scan_root = tmp_path / "failed-transaction-folder"
    scan_root.mkdir()
    (scan_root / "notes.txt").write_text("metadata", encoding="utf-8")

    with Session(database_engine) as database_session:
        owner = create_test_user(database_session, "transaction-owner")

        def reject_scan_commit(_database_session):
            raise SQLAlchemyError("simulated database commit failure")

        event.listen(database_session, "before_commit", reject_scan_commit)
        try:
            with pytest.raises(SQLAlchemyError, match="simulated database commit failure"):
                ScannerService(database_session).scan_folder_and_save_file_metadata(
                    scan_root, owner.id
                )
        finally:
            event.remove(database_session, "before_commit", reject_scan_commit)

    with Session(database_engine) as verification_session:
        assert verification_session.scalar(select(func.count()).select_from(File)) == 0
        assert verification_session.scalar(
            select(func.count()).select_from(SourceFolder)
        ) == 0


def test_unexpected_extraction_error_is_saved_as_failed_status(
    database_engine, tmp_path: Path, monkeypatch
):
    scan_root = tmp_path / "unexpected-extraction-folder"
    scan_root.mkdir()
    (scan_root / "notes.txt").write_text("test content", encoding="utf-8")

    with Session(database_engine) as database_session:
        owner = create_test_user(database_session, "extraction-owner")
        scan_result = ScannerService(
            database_session
        ).scan_folder_and_save_file_metadata(scan_root, owner.id)
        file_id = scan_result.files[0].file_id
        assert file_id is not None

        def raise_unexpected_extraction_error(_file_path):
            raise RuntimeError("parser implementation details")

        monkeypatch.setattr(
            file_content_service,
            "extract_file_content",
            raise_unexpected_extraction_error,
        )
        content_record = FileContentService(
            database_session
        ).extract_content_for_scanned_file(file_id, owner.id)
        assert content_record.extraction_status == "failed"
        assert content_record.extraction_error == "File content could not be extracted."

    with Session(database_engine) as verification_session:
        saved_content = verification_session.scalar(
            select(FileContent).where(FileContent.file_id == file_id)
        )
        assert saved_content is not None
        assert saved_content.extraction_status == "failed"
        assert saved_content.extracted_at is not None


def test_scanner_and_content_handlers_return_results_for_authenticated_owner(
    database_engine, tmp_path: Path
):
    scan_root = tmp_path / "api-folder"
    scan_root.mkdir()
    (scan_root / "hello.txt").write_text("API persisted text", encoding="utf-8")
    (scan_root / "bad.json").write_text("{", encoding="utf-8")
    (scan_root / "unknown.zip").write_bytes(b"zip")

    with Session(database_engine) as database_session:
        owner = create_test_user(database_session, "api-owner")
        scan_response = scanner_controller.scan_selected_folder(
            FolderScanRequest(folder_path=str(scan_root)),
            database_session,
            owner,
        )
        assert scan_response.files_discovered == 3
        assert scan_response.records_persisted == 3
        file_ids_by_name = {
            scanned_file.name: scanned_file.file_id
            for scanned_file in scan_response.files
        }

        extraction_response = file_content_controller.extract_content_for_file(
            file_ids_by_name["hello.txt"], database_session, owner
        )
        assert extraction_response.files_extracted == 1
        assert extraction_response.records_persisted == 1
        assert extraction_response.file_name == "hello.txt"
        assert extraction_response.file_type == ".txt"
        assert extraction_response.extracted_text == "API persisted text"

        # Fresh extraction must read the changed original and replace the
        # previously persisted value returned by the extraction endpoint.
        (scan_root / "hello.txt").write_text("Changed original text", encoding="utf-8")
        changed_response = file_content_controller.extract_content_for_file(
            file_ids_by_name["hello.txt"], database_session, owner
        )
        assert changed_response.extracted_text == "Changed original text"
        saved_changed_content = database_session.scalar(
            select(FileContent).where(
                FileContent.file_id == file_ids_by_name["hello.txt"]
            )
        )
        assert saved_changed_content.extracted_text == "Changed original text"

        # A removed original must not be reported as a successful extraction
        # or leave old text in the content record.
        (scan_root / "hello.txt").unlink()
        missing_response = file_content_controller.extract_content_for_file(
            file_ids_by_name["hello.txt"], database_session, owner
        )
        assert missing_response.extraction_status == "failed"
        assert missing_response.extracted_text is None
        assert missing_response.error
        failed_saved_content = database_session.scalar(
            select(FileContent).where(
                FileContent.file_id == file_ids_by_name["hello.txt"]
            )
        )
        assert failed_saved_content.extracted_text is None

        failed_extraction = file_content_controller.extract_content_for_file(
            file_ids_by_name["bad.json"], database_session, owner
        )
        assert failed_extraction.extraction_status == "failed"

        unsupported_extraction = file_content_controller.extract_content_for_file(
            file_ids_by_name["unknown.zip"], database_session, owner
        )
        assert unsupported_extraction.extraction_status == "unsupported"

        extracted_content = file_content_controller.get_extracted_content(
            file_ids_by_name["hello.txt"], database_session, owner
        )
        assert extracted_content.extraction_status == "failed"
        assert extracted_content.extracted_text is None


def test_user_cannot_extract_or_read_another_users_file(
    database_engine, tmp_path: Path
):
    first_user_folder = tmp_path / "first-user"
    first_user_folder.mkdir()
    (first_user_folder / "private.txt").write_text("private", encoding="utf-8")

    with Session(database_engine) as database_session:
        first_user = create_test_user(database_session, "first-user")
        second_user = create_test_user(database_session, "second-user")
        scan_result = ScannerService(
            database_session
        ).scan_folder_and_save_file_metadata(first_user_folder, first_user.id)
        private_file_id = scan_result.files[0].file_id
        assert private_file_id is not None
        content_service = FileContentService(database_session)

        with pytest.raises(FileNotFoundInDatabaseError):
            content_service.extract_content_for_scanned_file(
                private_file_id, second_user.id
            )
        with pytest.raises(FileNotFoundInDatabaseError):
            content_service.get_extracted_content(private_file_id, second_user.id)


def test_app_status_endpoint_reports_database_readiness():
    class DatabaseAvailability:
        def __init__(self, is_available: bool) -> None:
            self.is_available = is_available

        def is_database_available(self) -> bool:
            return self.is_available

    from app.main import app

    assert "/api/app/status" in app.openapi()["paths"]
    available_service = AppService()
    available_service.database_repository = DatabaseAvailability(True)
    assert get_app_status(available_service) == {"status": "ok"}

    unavailable_service = AppService()
    unavailable_service.database_repository = DatabaseAvailability(False)
    with pytest.raises(HTTPException) as unavailable:
        get_app_status(unavailable_service)
    assert unavailable.value.status_code == 503
