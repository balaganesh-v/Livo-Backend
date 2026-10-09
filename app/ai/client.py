"""Local document conversion and lightweight metadata analysis with Docling."""

import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from app.schemas.ai_analysis import AIAnalysisResult

MAX_DOCUMENT_BYTES = 100 * 1024 * 1024
MAX_DOCUMENT_CHARS = 200_000


class AIClient(Protocol):
    def analyze_file(self, context: dict[str, object]) -> tuple[AIAnalysisResult, str]: ...


class DoclingUnavailableError(RuntimeError):
    """Docling or its local OCR runtime is not installed correctly."""


class DoclingProcessingError(RuntimeError):
    """Docling could not convert the supplied file."""


@lru_cache(maxsize=1)
def _get_converter():
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import (
            PdfPipelineOptions,
            RapidOcrOptions,
        )
        from docling.document_converter import (
            DocumentConverter,
            ImageFormatOption,
            PdfFormatOption,
        )
        from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
    except ImportError as exc:
        raise DoclingUnavailableError(
            "Docling is not installed. Install the backend requirements and restart the service."
        ) from exc

    pdf_options = PdfPipelineOptions()
    pdf_options.do_ocr = True
    pdf_options.ocr_options = RapidOcrOptions()
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
            InputFormat.IMAGE: ImageFormatOption(
                pipeline_cls=StandardPdfPipeline,
                pipeline_options=pdf_options,
            ),
        }
    )


_STOP_WORDS = {
    "about", "after", "again", "also", "among", "because", "been", "before", "being",
    "between", "could", "does", "from", "have", "into", "more", "most", "other", "over",
    "should", "some", "such", "than", "that", "their", "there", "these", "they", "this",
    "through", "under", "upon", "very", "were", "what", "when", "where", "which", "while",
    "with", "would", "your", "document", "page", "file",
}
_TOPIC_TERMS = {
    "finance": {"invoice", "payment", "accounting", "budget", "tax", "bank", "receipt", "expense"},
    "education": {"lesson", "course", "student", "assignment", "lecture", "exam", "research", "thesis"},
    "technology": {"software", "system", "code", "database", "server", "network", "api", "computer"},
    "legal": {"agreement", "contract", "court", "legal", "clause", "attorney", "policy", "terms"},
    "health": {"medical", "health", "patient", "doctor", "hospital", "treatment", "diagnosis"},
    "business": {"company", "business", "project", "meeting", "client", "sales", "proposal", "report"},
}
_PERSONAL_TERMS = {"family", "personal", "home", "recipe", "diary", "travel", "photo", "health"}
_WORK_TERMS = {"company", "business", "project", "meeting", "client", "sales", "invoice", "work"}
_STUDY_TERMS = {"lesson", "course", "student", "assignment", "lecture", "exam", "research", "thesis"}


def _extract_text(file_path: Path, extension: str) -> str:
    try:
        if file_path.stat().st_size > MAX_DOCUMENT_BYTES:
            raise DoclingProcessingError("Files larger than 100 MB are not supported for analysis")
        if extension in {".txt", ".md", ".csv", ".json", ".xml", ".log"}:
            return file_path.read_text(encoding="utf-8", errors="replace")[:MAX_DOCUMENT_CHARS]
        document = _get_converter().convert(str(file_path)).document
        return document.export_to_text()[:MAX_DOCUMENT_CHARS]
    except (DoclingUnavailableError, DoclingProcessingError):
        raise
    except Exception as exc:
        raise DoclingProcessingError(
            "Docling could not read this file. Check that it is valid and supported."
        ) from exc


def _analyze_text(text: str, extension: str, filename: str) -> AIAnalysisResult:
    words = [word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text)]
    counts = Counter(word for word in words if word not in _STOP_WORDS)
    keywords = [word for word, _ in counts.most_common(10)]
    hits = {
        category: sorted(set(words).intersection(terms))
        for category, terms in _TOPIC_TERMS.items()
    }
    category, matched_terms = max(hits.items(), key=lambda item: len(item[1]))
    if not matched_terms:
        category = "document"
        matched_terms = []
        confidence = 0.25
    else:
        confidence = min(0.7, 0.35 + 0.1 * len(matched_terms))

    compact = " ".join(text.split())
    if not compact:
        raise DoclingProcessingError("No readable text could be extracted from this file")
    excerpt = compact[:260].rstrip()
    if len(compact) > len(excerpt):
        excerpt += "…"
    ext_label = extension.lstrip(".").upper() or "FILE"
    description = f"Locally extracted from {filename} ({ext_label}); labels are keyword-based. Excerpt: {excerpt}"
    return AIAnalysisResult(
        category=category.title(),
        subcategory=matched_terms[0].title() if matched_terms else None,
        description=description,
        keywords=keywords,
        confidence=confidence,
        content_type=f"{ext_label} document",
        is_personal=bool(set(words).intersection(_PERSONAL_TERMS)),
        is_work=bool(set(words).intersection(_WORK_TERMS)),
        is_study=bool(set(words).intersection(_STUDY_TERMS)),
    )


class DoclingClient:
    """Keep the analysis response contract without sending content to an API."""

    def analyze_file(self, context: dict[str, object]) -> tuple[AIAnalysisResult, str]:
        file_path = Path(str(context["file_path"]))
        extension = str(context.get("extension") or file_path.suffix).lower()
        try:
            text = _extract_text(file_path, extension)
        except OSError as exc:
            raise DoclingProcessingError("Could not access the selected file") from exc
        return _analyze_text(text, extension, str(context.get("filename") or file_path.name)), "docling-local-rules"
