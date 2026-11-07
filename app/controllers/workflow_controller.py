from pathlib import Path
import logging
import shutil
import os
import errno
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.connection import get_database_session
from app.models.organization_plan import OrganizationPlan, OrganizationPlanStatus
from app.models.organization_plan_item import OrganizationItemStatus, OrganizationPlanItem
from app.models.user import User
from app.schemas.workflow_schema import DestinationUpdate, PlanDecision, PreviewResponse, WorkflowStartRequest, WorkflowStartResponse, WorkflowStatusResponse
from app.security.authentication import get_current_user
from app.services.workflow_orchestrator import build_preview, create_workflow, get_workflow_for_user, run_organization_workflow

router = APIRouter(prefix="/api/workflows", tags=["Organization Workflows"])
logger = logging.getLogger(__name__)


def _move_without_overwrite(source: Path, destination: Path) -> None:
    """Move a regular file without ever replacing a destination created concurrently."""
    try:
        # AI_Organized is normally on the same volume as the source. link() is atomic
        # and fails if the destination already exists, avoiding overwrite races.
        os.link(source, destination)
        source.unlink()
    except OSError as exc:
        if exc.errno not in {errno.EXDEV, errno.EPERM, errno.EACCES, errno.ENOTSUP, errno.EOPNOTSUPP}:
            raise
        # Cross-volume / filesystems without hardlink support: reserve the new path
        # exclusively, copy its contents and metadata, then remove the source.
        created = False
        try:
            with source.open("rb") as source_stream, destination.open("xb") as destination_stream:
                created = True
                shutil.copyfileobj(source_stream, destination_stream)
                destination_stream.flush()
                os.fsync(destination_stream.fileno())
            shutil.copystat(source, destination)
            source.unlink()
        except Exception:
            if created:
                try:
                    destination.unlink()
                except OSError:
                    logger.exception("Could not clean up incomplete move destination=%s", destination)
            raise


@router.post("/{workflow_id}/move-files")
def move_approved_files(workflow_id: int, session: Session = Depends(get_database_session),
                        current_user: User = Depends(get_current_user)):
    """Move only approved plan files after the frontend has obtained explicit confirmation."""
    workflow = get_workflow_for_user(session, workflow_id, current_user.id)
    if workflow is None or workflow.plan_id is None:
        raise HTTPException(status_code=404, detail="Organization workflow not found.")
    plan = session.scalar(select(OrganizationPlan).where(
        OrganizationPlan.id == workflow.plan_id,
        OrganizationPlan.user_id == current_user.id,
    ).with_for_update())
    if plan is None:
        raise HTTPException(status_code=404, detail="Organization plan not found.")
    if plan.status == OrganizationPlanStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="This organization plan has already been executed.")
    if plan.status not in {OrganizationPlanStatus.APPROVED, OrganizationPlanStatus.FAILED}:
        raise HTTPException(status_code=409, detail="Approve and create the folders before moving files.")

    source_root = Path(plan.source_folder.folder_path).resolve()
    organized_root = (source_root / "AI_Organized").resolve()
    items = list(session.scalars(select(OrganizationPlanItem).where(
        OrganizationPlanItem.plan_id == plan.id,
    ).order_by(OrganizationPlanItem.id).with_for_update()))
    eligible = [item for item in items if item.action.value == "move" and item.status == OrganizationItemStatus.APPROVED]
    if not eligible:
        raise HTTPException(status_code=409, detail="There are no approved files available to move.")

    plan.status = OrganizationPlanStatus.EXECUTING
    session.commit()
    results = []
    for item in eligible:
        source_text = item.current_path
        destination_text = item.proposed_path or ""
        result = {"file_id": item.file_id, "file_name": Path(source_text).name,
                  "source_path": source_text, "destination_path": destination_text}
        try:
            source = Path(source_text).resolve(strict=False)
            destination = Path(destination_text).resolve(strict=False)
            source.relative_to(source_root)
            destination.relative_to(organized_root)
            if source == source_root or destination == organized_root:
                raise ValueError("Source or destination resolves to a folder root.")
            if destination.name != source.name:
                raise ValueError("Destination must preserve the original filename.")
            if not source.is_file():
                result.update(status="failed", error="Source file is missing or is not a regular file.")
                item.status = OrganizationItemStatus.FAILED
            elif not destination.parent.is_dir():
                result.update(status="failed", error="Approved destination folder does not exist.")
                item.status = OrganizationItemStatus.FAILED
            elif destination.exists():
                result.update(status="skipped", error="Destination already exists; no file was overwritten.")
                # Keep approved status so an operator can resolve the collision and retry.
                results.append(result)
                continue
            else:
                _move_without_overwrite(source, destination)
                if destination.is_file() and not source.exists():
                    item.status = OrganizationItemStatus.COMPLETED
                    item.current_path = str(destination)
                    item.file.file_path = str(destination)
                    item.executed_at = datetime.now()
                    result["status"] = "moved"
                else:
                    item.status = OrganizationItemStatus.FAILED
                    result.update(status="failed", error="Move could not be verified on disk.")
        except (OSError, ValueError, shutil.Error) as exc:
            item.status = OrganizationItemStatus.FAILED
            result.update(status="failed", error=str(exc))
        session.commit()
        results.append(result)

    succeeded = sum(entry["status"] == "moved" for entry in results)
    failed = sum(entry["status"] == "failed" for entry in results)
    skipped = sum(entry["status"] == "skipped" for entry in results)
    pending = any(item.status == OrganizationItemStatus.APPROVED for item in items)
    plan.status = OrganizationPlanStatus.FAILED if failed else (OrganizationPlanStatus.APPROVED if pending else OrganizationPlanStatus.COMPLETED)
    if not pending and not failed:
        plan.completed_at = datetime.now()
    session.commit()
    return {"workflow_id": workflow.id, "plan_id": plan.id,
            "status": "completed" if not pending and not failed else "partial" if succeeded else "failed",
            "total": len(results), "moved": succeeded, "failed": failed, "skipped": skipped,
            "files": results}


@router.post("/start", response_model=WorkflowStartResponse)
def start_workflow(request: WorkflowStartRequest, background_tasks: BackgroundTasks,
                   session: Session = Depends(get_database_session), current_user: User = Depends(get_current_user)):
    try:
        workflow = create_workflow(session, request.source_folder_id, current_user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except SQLAlchemyError as exc:
        session.rollback()
        logger.exception("Could not persist workflow start source_folder_id=%s user_id=%s", request.source_folder_id, current_user.id)
        raise HTTPException(
            status_code=503,
            detail="Workflow storage is unavailable. Restart the backend and apply the organization workflow database migration.",
        ) from exc
    if workflow.status == "pending":
        background_tasks.add_task(run_organization_workflow, workflow.id)
    return WorkflowStartResponse(workflow_id=workflow.id, status=workflow.status, stage=workflow.stage)


@router.get("/{workflow_id}/status", response_model=WorkflowStatusResponse)
def workflow_status(workflow_id: int, session: Session = Depends(get_database_session), current_user: User = Depends(get_current_user)):
    workflow = get_workflow_for_user(session, workflow_id, current_user.id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return WorkflowStatusResponse(workflow_id=workflow.id, source_folder_id=workflow.source_folder_id,
        status=workflow.status, stage=workflow.stage, total_files=workflow.total_files,
        extraction=workflow.extraction_counts or {}, categorization=workflow.categorization_counts or {},
        plan_id=workflow.plan_id, error_message=workflow.error_message)


@router.get("/{workflow_id}/preview", response_model=PreviewResponse)
def workflow_preview(workflow_id: int, session: Session = Depends(get_database_session), current_user: User = Depends(get_current_user)):
    workflow = get_workflow_for_user(session, workflow_id, current_user.id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    try:
        return build_preview(session, workflow)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.patch("/{workflow_id}/items/{file_id}")
def update_destination(workflow_id: int, file_id: int, request: DestinationUpdate,
                       session: Session = Depends(get_database_session), current_user: User = Depends(get_current_user)):
    workflow = get_workflow_for_user(session, workflow_id, current_user.id)
    if workflow is None or workflow.status != "preview_ready" or workflow.plan_id is None:
        raise HTTPException(status_code=404, detail="Editable preview not found.")
    item = session.scalar(select(OrganizationPlanItem).where(
        OrganizationPlanItem.plan_id == workflow.plan_id,
        OrganizationPlanItem.file_id == file_id,
    ))
    plan = session.scalar(select(OrganizationPlan).where(
        OrganizationPlan.id == workflow.plan_id,
        OrganizationPlan.user_id == current_user.id,
    ).with_for_update())
    if item is None or plan is None or plan.status != OrganizationPlanStatus.PENDING:
        raise HTTPException(status_code=404, detail="File is not part of this plan.")
    try:
        root = (Path(item.file.source_folder.folder_path).resolve() / "AI_Organized").resolve()
        candidate = Path(request.proposed_path).resolve()
    except OSError as exc:
        raise HTTPException(status_code=422, detail=f"Could not resolve the proposed destination: {exc}")
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=422, detail="Destination must remain inside the AI_Organized folder.")
    if candidate.name != item.file.name:
        raise HTTPException(status_code=422, detail="Destination must preserve the original filename.")
    item.proposed_path = str(candidate)
    session.commit()
    return {"workflow_id": workflow.id, "file_id": file_id, "proposed_path": item.proposed_path}


@router.post("/{workflow_id}/decision")
def decide_plan(workflow_id: int, request: PlanDecision,
                session: Session = Depends(get_database_session), current_user: User = Depends(get_current_user)):
    workflow = get_workflow_for_user(session, workflow_id, current_user.id)
    if workflow is None or workflow.status != "preview_ready" or workflow.plan_id is None:
        raise HTTPException(status_code=404, detail="Reviewable plan not found.")
    plan = session.scalar(select(OrganizationPlan).where(
        OrganizationPlan.id == workflow.plan_id,
        OrganizationPlan.user_id == current_user.id,
    ).with_for_update())
    if plan is None:
        raise HTTPException(status_code=404, detail="Organization plan not found.")
    if request.decision == "approve":
        if plan.status not in {OrganizationPlanStatus.PENDING, OrganizationPlanStatus.APPROVED}:
            raise HTTPException(status_code=409, detail=f"This plan cannot be approved from status {plan.status.value}.")

        try:
            source_root = Path(plan.source_folder.folder_path).resolve()
            organized_root = (source_root / "AI_Organized").resolve()
        except OSError as exc:
            raise HTTPException(status_code=422, detail=f"Could not resolve the selected source folder: {exc}")
        try:
            organized_root.relative_to(source_root)
        except ValueError:
            raise HTTPException(status_code=422, detail="The organization root resolves outside the selected folder.")

        # Retrieve all plan destinations, rebasing legacy plans beneath AI_Organized.
        normalized_destinations = []
        directories = {organized_root}
        for item in plan.items:
            if not item.proposed_path:
                continue
            try:
                raw_destination = Path(item.proposed_path).resolve()
            except OSError as exc:
                raise HTTPException(status_code=422, detail=f"Could not resolve proposed path {item.proposed_path}: {exc}")
            try:
                relative = raw_destination.relative_to(source_root)
            except ValueError:
                raise HTTPException(status_code=422, detail="A proposed destination is outside the selected folder.")
            if not relative.parts:
                raise HTTPException(status_code=422, detail="A proposed destination cannot be the selected folder itself.")
            if relative.parts[0].casefold() != "ai_organized":
                relative = Path("AI_Organized") / relative
            destination = (source_root / relative).resolve()
            try:
                destination.relative_to(organized_root)
            except ValueError:
                raise HTTPException(status_code=422, detail="A proposed destination is outside AI_Organized.")
            if destination.name != Path(item.current_path).name:
                raise HTTPException(status_code=422, detail="A proposed destination must preserve the original filename.")
            normalized_destinations.append((item, destination))
            directory = destination.parent
            while True:
                try:
                    directory.relative_to(organized_root)
                except ValueError:
                    raise HTTPException(status_code=422, detail="A proposed folder is outside AI_Organized.")
                directories.add(directory)
                if directory == organized_root:
                    break
                directory = directory.parent

        try:
            source_available = source_root.exists() and source_root.is_dir()
            source_error = f"Selected source folder is not available as a directory: {source_root}"
        except OSError as exc:
            source_available = False
            source_error = f"Cannot access selected source folder {source_root}: {exc}"
        if not source_available:
            results = []
            for directory in sorted(directories, key=lambda path: len(path.parts)):
                try:
                    exists, is_dir = directory.exists(), directory.is_dir()
                except OSError:
                    exists, is_dir = False, False
                results.append({"path": str(directory), "status": "failed", "exists": exists,
                                "is_dir": is_dir, "error": source_error})
            session.rollback()
            return {"workflow_id": workflow.id, "plan_id": plan.id,
                    "status": "creation_failed", "source_folder_path": str(source_root),
                    "organized_root_path": str(organized_root), "folders": results}

        results = []
        for directory in sorted(directories, key=lambda path: len(path.parts)):
            try:
                existed_before = directory.exists() and directory.is_dir()
                directory.mkdir(parents=True, exist_ok=True)
                exists = directory.exists()
                is_dir = directory.is_dir()
                if not exists or not is_dir:
                    results.append({"path": str(directory), "status": "failed",
                                    "error": "Path does not exist as a directory after creation."})
                else:
                    results.append({"path": str(directory),
                                    "status": "already_exists" if existed_before else "created",
                                    "exists": exists, "is_dir": is_dir})
            except OSError as exc:
                results.append({"path": str(directory), "status": "failed", "error": str(exc)})

        all_verified = all(result["status"] != "failed" for result in results)
        if all_verified:
            plan.status = OrganizationPlanStatus.APPROVED
            for item, destination in normalized_destinations:
                item.proposed_path = str(destination)
                item.status = OrganizationItemStatus.APPROVED
            session.commit()
        else:
            session.rollback()
        return {"workflow_id": workflow.id, "plan_id": plan.id,
                "status": "approved" if all_verified else "creation_failed",
                "source_folder_path": str(source_root),
                "organized_root_path": str(organized_root),
                "folders": results}
    else:
        if plan.status != OrganizationPlanStatus.PENDING:
            raise HTTPException(status_code=409, detail=f"This plan cannot be cancelled from status {plan.status.value}.")
        plan.status = OrganizationPlanStatus.CANCELLED
        for item in plan.items:
            item.status = OrganizationItemStatus.REJECTED
    session.commit()
    return {"workflow_id": workflow.id, "plan_id": plan.id, "status": plan.status.value,
            "folders": []}

