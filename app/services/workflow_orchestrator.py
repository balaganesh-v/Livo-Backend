from pathlib import Path
import logging

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.database.connection import SessionLocal
from app.models.file import File
from app.models.organization_plan import OrganizationPlan
from app.models.organization_plan_item import OrganizationPlanItem
from app.models.organization_workflow import OrganizationWorkflow
from app.models.source_folder import SourceFolder, SourceFolderStatus
from app.services.ai_analysis_service import AIAnalysisService
from app.services.file_content_service import FileContentService

ACTIVE_STATUSES = {"pending", "extracting", "categorizing", "generating_plan"}
logger = logging.getLogger(__name__)


def run_organization_workflow(workflow_id: int) -> None:
    """Run post-scan work in its own DB session; never touches the scan itself."""
    session = SessionLocal()
    try:
        claimed = session.execute(update(OrganizationWorkflow).where(
            OrganizationWorkflow.id == workflow_id,
            OrganizationWorkflow.status == "pending",
        ).values(status="extracting", stage="extracting"))
        session.commit()
        if not claimed.rowcount:
            return
        workflow = session.get(OrganizationWorkflow, workflow_id)
        files = list(session.scalars(select(File).where(
            File.source_folder_id == workflow.source_folder_id,
            File.user_id == workflow.user_id,
            File.is_deleted.is_(False),
        ).order_by(File.id)))
        workflow.total_files = len(files)
        counts = {"completed": 0, "empty": 0, "unsupported": 0, "failed": 0}
        session.commit()
        content_service = FileContentService(session)
        for file_record in files:
            try:
                content = content_service.extract_content_for_scanned_file(file_record.id, workflow.user_id)
                status = content.extraction_status
                if status in {"completed", "truncated"}:
                    counts["completed" if (content.extracted_text or "").strip() else "empty"] += 1
                elif status == "unsupported":
                    counts["unsupported"] += 1
                else:
                    counts["failed"] += 1
            except Exception:
                session.rollback()
                counts["failed"] += 1
            workflow = session.get(OrganizationWorkflow, workflow_id)
            workflow.extraction_counts = counts
            session.commit()

        workflow = session.get(OrganizationWorkflow, workflow_id)
        workflow.stage = workflow.status = "categorizing"
        workflow.categorization_counts = {"completed": 0, "low_confidence": 0, "failed": 0, "manual_review": 0}
        session.commit()

        def update_categorization(counts):
            current = session.get(OrganizationWorkflow, workflow_id)
            if counts.get("stage") == "generating_plan":
                current.status = current.stage = "generating_plan"
            current.categorization_counts = {key: value for key, value in counts.items() if key != "stage"}
            session.commit()

        result = AIAnalysisService(session).analyze_source_folder(
            workflow.source_folder_id,
            workflow.user_id,
            reanalyze=False,
            progress_callback=update_categorization,
        )
        workflow = session.get(OrganizationWorkflow, workflow_id)
        if result.get("status") == "failed":
            raise RuntimeError("AI categorization failed for every eligible file; verify the configured Ollama model.")
        if result.get("plan_id") is None:
            raise RuntimeError("No organization plan was saved.")
        workflow.stage = "preview_ready"
        workflow.status = "preview_ready"
        workflow.plan_id = result["plan_id"]
        workflow.review_files = [
            {**entry, "review_reason": entry.get("reason")}
            for entry in [*result.get("skipped_files", []), *result.get("failed_files", [])]
        ]
        session.commit()
    except Exception as exc:
        logger.exception("Organization workflow failed workflow_id=%s", workflow_id)
        session.rollback()
        workflow = session.get(OrganizationWorkflow, workflow_id)
        if workflow:
            workflow.status = "failed"
            workflow.error_message = str(exc) if isinstance(exc, RuntimeError) else "Workflow processing failed. Check backend logs for details."
            session.commit()
    finally:
        session.close()


def create_workflow(session: Session, source_folder_id: int, user_id: int) -> OrganizationWorkflow:
    folder = session.scalar(select(SourceFolder).where(
        SourceFolder.id == source_folder_id,
        SourceFolder.user_id == user_id,
        SourceFolder.status == SourceFolderStatus.COMPLETED,
    ))
    if folder is None:
        raise LookupError("Completed scan folder not found.")
    existing = session.scalar(select(OrganizationWorkflow).where(
        OrganizationWorkflow.source_folder_id == source_folder_id,
        OrganizationWorkflow.user_id == user_id,
    ).order_by(OrganizationWorkflow.id.desc()))
    if existing:
        return existing
    workflow = OrganizationWorkflow(user_id=user_id, source_folder_id=source_folder_id)
    session.add(workflow)
    try:
        session.commit()
    except Exception:
        session.rollback()
        existing = session.scalar(select(OrganizationWorkflow).where(
            OrganizationWorkflow.source_folder_id == source_folder_id,
            OrganizationWorkflow.user_id == user_id,
        ))
        if existing:
            return existing
        raise
    session.refresh(workflow)
    return workflow


def get_workflow_for_user(session: Session, workflow_id: int, user_id: int) -> OrganizationWorkflow | None:
    return session.scalar(select(OrganizationWorkflow).where(
        OrganizationWorkflow.id == workflow_id,
        OrganizationWorkflow.user_id == user_id,
    ))


def build_preview(session: Session, workflow: OrganizationWorkflow) -> dict:
    if workflow.status != "preview_ready" or workflow.plan_id is None:
        raise ValueError("Organization preview is not ready.")
    plan = session.scalar(select(OrganizationPlan).options(
        joinedload(OrganizationPlan.items).joinedload(OrganizationPlanItem.file).joinedload(File.ai_analysis)
    ).where(OrganizationPlan.id == workflow.plan_id, OrganizationPlan.user_id == workflow.user_id))
    if plan is None:
        raise LookupError("Organization plan not found.")
    valid_file_ids = set(session.scalars(select(File.id).where(
        File.source_folder_id == workflow.source_folder_id,
        File.user_id == workflow.user_id,
    )))
    rows = []
    root = Path(plan.source_folder.folder_path).resolve()
    organized_root = (root / "AI_Organized").resolve()
    tree = {"name": root.name, "path": str(root), "type": "folder", "children": []}
    node_lookup = {(): tree}
    proposed_folders = set()
    for item in plan.items:
        if item.file_id not in valid_file_ids or not item.proposed_path:
            continue
        proposed = Path(item.proposed_path).resolve()
        try:
            relative = proposed.relative_to(root)
        except ValueError:
            continue
        # Rebase plans created by older versions beneath the dedicated root.
        if not relative.parts or relative.parts[0].casefold() != "ai_organized":
            relative = Path("AI_Organized") / relative
            proposed = (root / relative).resolve()
        try:
            proposed.relative_to(organized_root)
        except ValueError:
            continue
        file_record = item.file
        analysis = file_record.ai_analysis
        segments = relative.parts
        if not segments or segments[-1] != file_record.name:
            continue
        row = {
            "file_id": file_record.id,
            "file_name": file_record.name,
            "original_path": item.current_path,
            "proposed_path": str(proposed),
            "category": analysis.category if analysis else None,
            "subcategory": analysis.subcategory if analysis else None,
            "description": analysis.description if analysis else None,
            "keywords": analysis.keywords or [] if analysis else [],
            "confidence": float(analysis.confidence) if analysis and analysis.confidence is not None else None,
            "needs_review": not analysis or analysis.confidence is None or float(analysis.confidence) < 0.65,
            "review_reason": "Confidence is below the review threshold." if analysis and analysis.confidence is not None and float(analysis.confidence) < 0.65 else None,
        }
        rows.append(row)
        parent = tree
        path_parts = ()
        for segment in segments[:-1]:
            path_parts += (segment,)
            proposed_folders.add(str(root.joinpath(*path_parts)))
            if path_parts not in node_lookup:
                child = {"name": segment, "path": str(root.joinpath(*path_parts)), "type": "folder", "children": []}
                parent["children"].append(child)
                node_lookup[path_parts] = child
            parent = node_lookup[path_parts]
        parent["children"].append({"name": file_record.name, "path": str(proposed), "type": "file", **row})
    for review in workflow.review_files or []:
        file_record = session.scalar(select(File).where(
            File.id == review.get("file_id"),
            File.source_folder_id == workflow.source_folder_id,
            File.user_id == workflow.user_id,
        ))
        if file_record is None or any(row["file_id"] == file_record.id for row in rows):
            continue
        rows.append({
            "file_id": file_record.id,
            "file_name": file_record.name,
            "original_path": file_record.file_path,
            "proposed_path": "",
            "category": None,
            "subcategory": None,
            "description": None,
            "keywords": [],
            "confidence": None,
            "needs_review": True,
            "review_reason": review.get("review_reason") or "This file needs manual review.",
        })
    # Always include the root, even when there are no categorized files.
    proposed_folders.add(str(organized_root))
    for folder_path in sorted(proposed_folders, key=lambda value: len(Path(value).parts)):
        relative_folder = Path(folder_path).relative_to(root)
        parent = tree
        path_parts = ()
        for segment in relative_folder.parts:
            path_parts += (segment,)
            if path_parts not in node_lookup:
                child = {"name": segment, "path": str(root.joinpath(*path_parts)), "type": "folder", "children": []}
                parent["children"].append(child)
                node_lookup[path_parts] = child
            parent = node_lookup[path_parts]
    return {"workflow_id": workflow.id, "plan_id": plan.id, "status": plan.status.value if hasattr(plan.status, "value") else plan.status,
            "source_folder_path": str(root), "organized_root_path": str(organized_root),
            "proposed_folders": sorted(proposed_folders),
            "categorized_files": [row for row in rows if row["proposed_path"]],
            "files_needing_review": [row for row in rows if row["needs_review"]], "tree": tree}

