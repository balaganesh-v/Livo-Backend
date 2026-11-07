from pydantic import BaseModel, ConfigDict, Field


class WorkflowStartRequest(BaseModel):
    source_folder_id: int = Field(gt=0)


class WorkflowStartResponse(BaseModel):
    workflow_id: int
    status: str
    stage: str


class WorkflowStatusResponse(BaseModel):
    workflow_id: int
    source_folder_id: int
    status: str
    stage: str
    total_files: int
    extraction: dict[str, int]
    categorization: dict[str, int]
    plan_id: int | None = None
    error_message: str | None = None


class PreviewFile(BaseModel):
    file_id: int
    file_name: str
    original_path: str
    proposed_path: str
    category: str | None = None
    subcategory: str | None = None
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    confidence: float | None = None
    needs_review: bool
    review_reason: str | None = None


class PreviewResponse(BaseModel):
    workflow_id: int
    plan_id: int
    status: str
    source_folder_path: str
    organized_root_path: str
    proposed_folders: list[str] = Field(default_factory=list)
    categorized_files: list[PreviewFile]
    files_needing_review: list[PreviewFile]
    tree: dict


class DestinationUpdate(BaseModel):
    proposed_path: str = Field(min_length=1, max_length=2048)


class PlanDecision(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")

