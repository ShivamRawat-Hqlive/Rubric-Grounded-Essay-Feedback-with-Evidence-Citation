"""Request and response models for AI evaluations."""

import math
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.db.models.evaluation import EvaluationStatus


class EvaluationCreateRequest(BaseModel):
    rubric_version_id: UUID


class EvidenceQuoteOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: UUID
    quoted_text: str = Field(min_length=1, max_length=2_000)
    reason: str = Field(min_length=1, max_length=1_000)

    @field_validator("quoted_text", "reason")
    @classmethod
    def require_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence text must not be empty")
        return value


class ClaimEvaluationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=1_000)
    evidence_quotes: list[EvidenceQuoteOutput] = Field(max_length=5)

    @field_validator("text")
    @classmethod
    def require_non_whitespace_claim(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim text must not be empty")
        return value


class CriterionEvaluationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: str
    score: float
    rationale: str
    strengths: list[str]
    weaknesses: list[str]
    suggestions: list[str]
    claims: list[ClaimEvaluationOutput] = Field(min_length=1, max_length=5)

    @field_validator("score", mode="before")
    @classmethod
    def require_numeric_score(cls, value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("score must be a JSON number")
        return value

    @field_validator("score")
    @classmethod
    def require_finite_score(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("score must be finite")
        return value

    @field_validator("criterion_id")
    @classmethod
    def require_criterion_id(cls, value: str) -> str:
        if not value or len(value) > 64:
            raise ValueError("criterion_id is invalid")
        return value

    @field_validator("rationale")
    @classmethod
    def require_rationale(cls, value: str) -> str:
        if not value.strip() or len(value) > 5_000:
            raise ValueError("rationale must contain 1 to 5000 characters")
        return value

    @field_validator("strengths", "weaknesses", "suggestions", mode="before")
    @classmethod
    def validate_feedback_list(cls, value: object) -> object:
        if (
            not isinstance(value, list)
            or len(value) > 5
            or any(not isinstance(item, str) or not item.strip() or len(item) > 1_000 for item in value)
        ):
            raise ValueError("feedback must be a list of at most five non-empty strings")
        return value

    @model_validator(mode="after")
    def require_actionable_suggestion(self) -> "CriterionEvaluationOutput":
        if not self.strengths or not self.weaknesses or not self.suggestions:
            raise ValueError(
                "strengths, weaknesses, and actionable suggestions cannot be empty"
            )
        return self


class EvidenceCitationResponse(BaseModel):
    source_chunk_id: UUID
    quoted_text: str
    model_relevance_rationale: str
    existence_status: Literal["verified"]
    relevance_status: Literal["unverified"]
    extracted_char_start: int
    extracted_char_end: int
    normalized_char_start: int
    normalized_char_end: int
    paragraph_start: int | None
    paragraph_end: int | None
    page_start: int | None
    page_end: int | None


class ClaimResponse(BaseModel):
    text: str
    evidence_quotes: list[EvidenceCitationResponse]


class FacultyCriterionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    faculty_score: Decimal | None = Field(
        default=None,
        max_digits=12,
        decimal_places=4,
    )
    faculty_rationale: str | None = Field(default=None, max_length=5_000)
    faculty_strengths: list[str] | None = Field(default=None, max_length=5)
    faculty_weaknesses: list[str] | None = Field(default=None, max_length=5)
    faculty_suggestions: list[str] | None = Field(default=None, max_length=5)

    @field_validator("faculty_score")
    @classmethod
    def require_finite_faculty_score(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and not value.is_finite():
            raise ValueError("faculty_score must be finite")
        return value

    @field_validator("faculty_rationale")
    @classmethod
    def validate_faculty_rationale(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value

    @field_validator(
        "faculty_strengths",
        "faculty_weaknesses",
        "faculty_suggestions",
        mode="before",
    )
    @classmethod
    def validate_faculty_feedback_list(
        cls,
        value: object,
    ) -> object:
        if value is None:
            return None
        if (
            not isinstance(value, list)
            or any(
                not isinstance(item, str) or not item.strip() or len(item) > 1_000
                for item in value
            )
        ):
            raise ValueError(
                "faculty feedback must be a list of non-empty strings"
            )
        return [item.strip() for item in value]

    @model_validator(mode="after")
    def require_update(self) -> "FacultyCriterionUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one faculty field must be provided.")
        return self


class FacultyReviewActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["approved", "rejected", "changes_requested"]
    notes: str | None = Field(default=None, max_length=5_000)

    @field_validator("notes")
    @classmethod
    def validate_optional_notes(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value


class FacultyReviewNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    notes: str = Field(min_length=1, max_length=5_000)


class EvaluationReviewEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    faculty_id: UUID
    criterion_score_id: UUID | None
    action: Literal[
        "note_added",
        "criterion_updated",
        "approved",
        "rejected",
        "changes_requested",
    ]
    notes: str | None
    created_at: datetime


class ReviewQueueItem(BaseModel):
    evaluation_id: UUID
    essay_id: UUID
    student_id: UUID
    course_id: UUID
    rubric_version_id: UUID
    evaluation_mode: Literal["openai", "mock"]
    status: EvaluationStatus
    started_at: datetime
    completed_at: datetime | None


class CriterionScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    criterion_id: UUID
    ai_score: Decimal
    ai_rationale: str
    strengths: list[str]
    weaknesses: list[str]
    suggestions: list[str]
    claims: list[ClaimResponse]
    faculty_score: Decimal | None
    faculty_rationale: str | None
    faculty_strengths: list[str] | None
    faculty_weaknesses: list[str] | None
    faculty_suggestions: list[str] | None


class EvaluationResponse(BaseModel):
    id: UUID
    essay_id: UUID
    rubric_version_id: UUID
    requested_by_id: UUID
    evaluation_mode: Literal["openai", "mock"]
    status: EvaluationStatus
    ai_total_score: Decimal | None
    faculty_total_score: Decimal | None
    has_unsupported_flags: bool
    error_code: str | None
    started_at: datetime
    completed_at: datetime | None
    criterion_scores: list[CriterionScoreResponse]
    review_history: list[EvaluationReviewEventResponse] = Field(default_factory=list)
