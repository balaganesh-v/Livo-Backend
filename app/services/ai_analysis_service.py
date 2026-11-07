from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from pathlib import Path
import re

from app.database.config import settings
from app.repositories.ai_analysis_repository import AIAnalysisRepository
from app.repositories.file_content_repository import FileContentRepository
from app.repositories.file_repository import FileRepository
from app.models.organization_plan import OrganizationPlan
from app.models.organization_plan_item import OrganizationPlanItem
from app.services.file_content_service import FileContentService
from app.services.ollama_service import (
    OllamaConnectionError,
    OllamaResponseError,
    OllamaService,
    OllamaTimeoutError,
)


class FileNotFoundForAnalysisError(Exception):
    pass


class ExtractedContentUnavailableError(Exception):
    pass


class ExtractionFailedError(Exception):
    pass


class EmptyExtractedContentError(Exception):
    pass


class AIAnalysisService:
    def __init__(self, session: Session, ollama_service: OllamaService | None = None):
        self.session = session
        self.files = FileRepository(session)
        self.contents = FileContentRepository(session)
        self.analyses = AIAnalysisRepository(session)
        self.ollama = ollama_service or OllamaService()
        self.content_service = FileContentService(session)

    def analyze_file(self, file_id: int, user_id: int):
        file_record = self.files.get_file_by_id(file_id, user_id)
        if (
            file_record is None
            or file_record.source_folder is None
            or file_record.source_folder.user_id != user_id
        ):
            raise FileNotFoundForAnalysisError
        content = self.contents.get_file_content_by_file_id(file_id)
        if content is None:
            raise ExtractedContentUnavailableError
        if content.extraction_status == "failed":
            raise ExtractionFailedError
        if content.extraction_status not in {"completed", "truncated"}:
            raise ExtractedContentUnavailableError
        if not (content.extracted_text or "").strip():
            raise EmptyExtractedContentError

        result = self.ollama.analyze(content.extracted_text)
        values = result.model_dump()
        values["model_used"] = settings.ollama_model
        try:
            return self.analyses.save(file_id, values)
        except Exception:
            self.session.rollback()
            raise

    def analyze_source_folder(self, folder_id: int, user_id: int, reanalyze: bool = False, progress_callback=None):
        folder = self.files.get_source_folder_for_user(folder_id, user_id)
        if folder is None:
            raise FileNotFoundForAnalysisError

        files = self.files.get_files_in_source_folder(folder_id, user_id)
        file_details = [(file.id, file.name) for file in files]
        existing = self.analyses.get_file_ids_with_analysis(
            [file_id for file_id, _ in file_details]
        )
        skipped = []
        failed = []
        analyzed_ids = []
        eligible_count = 0
        usable = []
        categorized_count = 0
        low_confidence_count = 0
        processed_count = 0

        for file_id, file_name in file_details:
            if file_id in existing and not reanalyze:
                analysis = self.analyses.get_by_file_id(file_id)
                if analysis and analysis.category and analysis.subcategory:
                    eligible_count += 1
                    usable.append((next(f for f in files if f.id == file_id), analysis))
                    categorized_count += 1
                    low_confidence_count += int(analysis.confidence is None or float(analysis.confidence) < 0.65)
                    processed_count += 1
                    if progress_callback:
                        progress_callback({"completed": categorized_count, "low_confidence": low_confidence_count, "failed": len(failed), "manual_review": len(skipped) + len(failed), "processed": processed_count, "total": len(files)})
                    continue

            content = self.contents.get_file_content_by_file_id(file_id)
            if content is None or content.extraction_status not in {"completed", "truncated"}:
                try:
                    content = self.content_service.extract_content_for_scanned_file(file_id, user_id)
                except Exception:
                    content = self.contents.get_file_content_by_file_id(file_id)
            if content is None:
                skipped.append({"file_id": file_id, "file_name": file_name, "reason": "Extracted content is unavailable."})
                processed_count += 1
                if progress_callback: progress_callback({"completed": categorized_count, "low_confidence": low_confidence_count, "failed": len(failed), "manual_review": len(skipped) + len(failed), "processed": processed_count, "total": len(files)})
                continue
            if content.extraction_status == "failed":
                skipped.append({"file_id": file_id, "file_name": file_name, "reason": "Content extraction failed."})
                processed_count += 1
                if progress_callback: progress_callback({"completed": categorized_count, "low_confidence": low_confidence_count, "failed": len(failed), "manual_review": len(skipped) + len(failed), "processed": processed_count, "total": len(files)})
                continue
            if content.extraction_status not in {"completed", "truncated"}:
                skipped.append({"file_id": file_id, "file_name": file_name, "reason": f"Content extraction status is {content.extraction_status}."})
                processed_count += 1
                if progress_callback: progress_callback({"completed": categorized_count, "low_confidence": low_confidence_count, "failed": len(failed), "manual_review": len(skipped) + len(failed), "processed": processed_count, "total": len(files)})
                continue
            extracted_text = content.extracted_text or ""
            if not extracted_text.strip():
                skipped.append({"file_id": file_id, "file_name": file_name, "reason": "Extracted content is empty."})
                processed_count += 1
                if progress_callback: progress_callback({"completed": categorized_count, "low_confidence": low_confidence_count, "failed": len(failed), "manual_review": len(skipped) + len(failed), "processed": processed_count, "total": len(files)})
                continue

            eligible_count += 1
            try:
                file_record = self.files.get_file_by_id(file_id, user_id)
                result = self.ollama.analyze(
                    extracted_text,
                    metadata={
                        "file_id": str(file_id),
                        "file_name": file_name,
                        "extension": file_record.extension if file_record else None,
                        "mime_type": file_record.mime_type if file_record else None,
                    },
                )
                values = result.model_dump()
                values["model_used"] = settings.ollama_model
                analysis = self.analyses.save(file_id, values)
                analyzed_ids.append(file_id)
                usable.append((next(f for f in files if f.id == file_id), analysis))
                categorized_count += 1
                low_confidence_count += int(analysis.confidence is None or float(analysis.confidence) < 0.65)
            except (OllamaConnectionError, OllamaTimeoutError, OllamaResponseError) as exc:
                failed.append({"file_id": file_id, "file_name": file_name, "reason": _safe_ollama_failure(exc)})
            except SQLAlchemyError:
                self.session.rollback()
                failed.append({"file_id": file_id, "file_name": file_name, "reason": "Could not save analysis due to a database error."})
            except Exception:
                self.session.rollback()
                failed.append({"file_id": file_id, "file_name": file_name, "reason": "Analysis failed unexpectedly."})
            processed_count += 1
            if progress_callback:
                progress_callback({"completed": categorized_count, "low_confidence": low_confidence_count, "failed": len(failed), "manual_review": len(skipped) + len(failed) + low_confidence_count, "processed": processed_count, "total": len(files)})

        if progress_callback:
            progress_callback({"stage": "generating_plan", "completed": categorized_count,
                               "low_confidence": low_confidence_count, "failed": len(failed),
                               "manual_review": len(skipped) + len(failed) + low_confidence_count,
                               "processed": processed_count, "total": len(files)})
        plan = self._save_organization_plan(folder_id, user_id, usable)
        status = "completed"
        if failed:
            status = "partial" if analyzed_ids or skipped else "failed"
        return {
            "source_folder_id": folder_id,
            "total_files": len(file_details),
            "eligible_files": eligible_count,
            "analyzed_files": len(analyzed_ids),
            "skipped_files": skipped,
            "failed_files": failed,
            "analyzed_file_ids": analyzed_ids,
            "status": status,
            "plan_id": plan.id,
            "subfolders": self._serialize_plan(plan),
        }

    def _save_organization_plan(self, folder_id: int, user_id: int, usable):
        plan = OrganizationPlan(user_id=user_id, source_folder_id=folder_id, total_files=len(usable))
        self.session.add(plan)
        self.session.flush()
        for file_record, analysis in usable:
            category = _safe_folder_segment(_category_label(analysis.category))
            subcategory = _safe_folder_segment(analysis.subcategory or "Other")
            proposed = str(Path(file_record.source_folder.folder_path) / "AI_Organized" / category / subcategory / file_record.name)
            self.session.add(OrganizationPlanItem(
                plan_id=plan.id, file_id=file_record.id, current_path=file_record.file_path,
                proposed_path=proposed, reason=analysis.description,
                confidence=analysis.confidence,
            ))
        self.session.commit()
        self.session.refresh(plan)
        return plan

    def _serialize_plan(self, plan):
        grouped = {}
        for item in plan.items:
            grouped.setdefault(Path(item.proposed_path or "").parent.name, []).append({
                "file_id": item.file_id, "file_name": Path(item.current_path).name,
                "reason": item.reason,
            })
        return [{"name": name, "files": entries} for name, entries in grouped.items()]


def _safe_ollama_failure(error: Exception) -> str:
    if isinstance(error, OllamaTimeoutError):
        return "Ollama analysis timed out."
    if isinstance(error, OllamaConnectionError):
        return "Cannot connect to Ollama or the configured model is unavailable."
    return "Ollama returned invalid analysis data."


def _group_name(analysis) -> str:
    category = (analysis.category or "").lower()
    detail = " ".join((analysis.subcategory or "", analysis.content_type or "", " ".join(analysis.keywords or []))).lower()
    if category == "study_materials":
        return "Education"
    if category == "work_documents":
        return "Work & Projects"
    if category == "software_files":
        if any(word in detail for word in ("config", "configuration", "settings", "environment", "yaml", "json", "toml")):
            return "Configuration"
        if any(word in detail for word in ("code", "program", "script", "source", "software", "developer")):
            return "Programming"
    label = (analysis.subcategory or analysis.category or "Other").strip()
    label = re.sub(r"[_-]+", " ", label)
    label = re.sub(r"\s+", " ", label).title()
    return label[:80] or "Other"


def _category_label(category: str | None) -> str:
    labels = {
        "study_materials": "Study", "work_documents": "Work", "personal_documents": "Personal",
        "financial_documents": "Finance", "software_files": "Software", "other": "Others",
    }
    return labels.get((category or "").lower(), (category or "Others").replace("_", " ").title())


def _safe_folder_segment(value: str) -> str:
    # Treat model output as untrusted path text and retain only a readable leaf name.
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value[:80] or "Other"
