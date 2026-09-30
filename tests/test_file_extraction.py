"""Focused tests for Day 5 extraction helpers."""

from pathlib import Path
import tempfile
import unittest

from docx import Document
from pypdf import PdfWriter

from app.file_processing.extraction.extractor import detect_file_type, extract_file_content
from app.file_processing.extraction.text_extractor import extract_text_file
from app.services.file_scanner_service import FileScannerService


class FileExtractionTests(unittest.TestCase):
    def test_text_extraction_and_invalid_encoding(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "note.txt"
            path.write_bytes(b"hello\xffworld")
            result = extract_file_content(path)
            self.assertTrue(result["success"])
            self.assertIn("\ufffd", result["content"])

    def test_large_text_is_marked_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.log"
            path.write_text("0123456789", encoding="utf-8")
            result = extract_text_file(path, max_bytes=5)
            self.assertTrue(result["truncated"])
            self.assertEqual(result["content"], "01234")

    def test_pdf_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            with path.open("wb") as stream:
                writer.write(stream)
            result = extract_file_content(path)
            self.assertTrue(result["success"])
            self.assertEqual(result["content"], "")
            self.assertIsNotNone(result["error"])

    def test_docx_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.docx"
            document = Document()
            document.add_paragraph("Document text")
            document.save(path)
            result = extract_file_content(path)
            self.assertTrue(result["success"])
            self.assertEqual(result["content"], "Document text")

    def test_classification(self) -> None:
        cases = {
            "photo.png": "image",
            "bundle.zip": "archive",
            "installer.exe": "executable",
            "payload.unknownext": "unknown",
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(detect_file_type(filename), expected)

    def test_missing_file_fails_cleanly(self) -> None:
        result = extract_file_content(Path("missing-file.txt"))
        self.assertFalse(result["success"])
        self.assertIsNotNone(result["error"])

    def test_existing_scanner_service_still_scans(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "note.txt").write_text("hello", encoding="utf-8")
            result = FileScannerService().scan(directory)
            self.assertEqual(result.total_files, 1)
            self.assertEqual(result.processed_files, 1)
            self.assertIsNotNone(result.files[0].file_hash)


if __name__ == "__main__":
    unittest.main()
