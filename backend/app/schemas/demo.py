"""Local portfolio-demo evaluation response contracts."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class DemoPageMetadata(BaseModel):
    page_number: int | None
    extracted_char_start: int
    extracted_char_end: int
    extraction_method: Literal["native", "ocr"]


class DemoEvidenceQuote(BaseModel):
    quoted_text: str
    extracted_char_start: int
    extracted_char_end: int
    page_number: int | None
    existence_verified: bool


class DemoCriterionResult(BaseModel):
    name: str
    description: str
    weight_percent: int
    score: int
    max_score: int
    weighted_score: float
    basis: str
    strengths: list[str]
    areas_to_improve: list[str]
    suggestions: list[str]
    evidence_quotes: list[DemoEvidenceQuote]


class DemoEvaluationResponse(BaseModel):
    id: str
    filename: str
    created_at: datetime
    evaluation_mode: Literal["local_demo"]
    demo_label: Literal["DEMO-GENERATED — NOT AI"]
    status: Literal["needs_review", "changes_requested", "approved"]
    extracted_text: str
    extractor_name: str
    page_map: list[DemoPageMetadata]
    total_score: float
    max_total_score: int
    criteria: list[DemoCriterionResult]
    faculty_note: str | None


class DemoReviewRequest(BaseModel):
    action: Literal["approved", "changes_requested"]
    note: str | None = Field(default=None, max_length=1000)
