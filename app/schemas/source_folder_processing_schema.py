from pydantic import BaseModel


class SourceFolderFileProcessResult(BaseModel):
    file_id: int
    file_name: str
    extraction_status: str
    category: str | None = None
    error: str | None = None


class SourceFolderProcessResponse(BaseModel):
    source_folder_id: int
    total_files: int
    extracted_files: int
    categorized_files: int
    unsupported_files: int
    failed_files: int
    results: list[SourceFolderFileProcessResult]
