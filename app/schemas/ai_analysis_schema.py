from typing import Literal

from pydantic import BaseModel, Field

AnalysisCategory = Literal[
    "study_materials",
    "work_documents",
    "personal_documents",
    "financial_documents",
    "software_files",
    "other",
]


class AIAnalysisResult(BaseModel):
    category: AnalysisCategory
    subcategory: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    keywords: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    content_type: str = Field(min_length=1, max_length=100)
    model_used: str = Field(min_length=1, max_length=100)


class AIAnalysisResponse(AIAnalysisResult):
    file_id: int


class BulkAIAnalysisRequest(BaseModel):
    source_folder_id: int = Field(gt=0)
    reanalyze: bool = False


class BulkAIAnalysisFileResult(BaseModel):
    file_id: int
    file_name: str
    reason: str


class OrganizationPlannedFile(BaseModel):
    file_id: int
    file_name: str
    reason: str | None = None


class OrganizationSubfolder(BaseModel):
    name: str
    files: list[OrganizationPlannedFile]


class BulkAIAnalysisResponse(BaseModel):
    source_folder_id: int
    total_files: int
    eligible_files: int
    analyzed_files: int
    skipped_files: list[BulkAIAnalysisFileResult]
    failed_files: list[BulkAIAnalysisFileResult]
    analyzed_file_ids: list[int]
    status: str
    plan_id: int
    subfolders: list[OrganizationSubfolder]
