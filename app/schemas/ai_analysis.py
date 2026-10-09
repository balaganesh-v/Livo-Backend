"""Validated schemas for AI generated file understanding."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AIAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    subcategory: str | None
    description: str
    keywords: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    content_type: str
    is_personal: bool
    is_work: bool
    is_study: bool

    @field_validator("category", "description", "content_type")
    @classmethod
    def must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("subcategory")
    @classmethod
    def normalize_subcategory(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class AIAnalysisResponse(BaseModel):
    file_id: int
    analysis: AIAnalysisResult
