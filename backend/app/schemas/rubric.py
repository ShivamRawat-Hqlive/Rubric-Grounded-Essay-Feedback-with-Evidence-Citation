"""Validated rubric, version, and criterion API schemas."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.db.models.rubric import RubricStatus

WEIGHT_TOTAL = Decimal("1")
WEIGHT_TOLERANCE = Decimal("0.000001")


class RubricCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    course_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)


class RubricPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_patch(self) -> "RubricPatchRequest":
        if not self.model_fields_set:
            raise ValueError("At least one rubric field must be provided.")
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("The rubric title cannot be null.")
        return self


class RubricLevelInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    score: Decimal = Field(max_digits=12, decimal_places=4)
    description: str = Field(min_length=1, max_length=1000)

    @field_validator("score")
    @classmethod
    def score_must_be_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("A score level must use a finite score.")
        return value


class RubricCriterionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=5000)
    min_score: Decimal = Field(default=Decimal("0"), max_digits=12, decimal_places=4)
    max_score: Decimal = Field(gt=0, max_digits=12, decimal_places=4)
    weight: Decimal = Field(gt=0, le=1, max_digits=7, decimal_places=6)
    sort_order: int = Field(ge=0, le=10000)
    levels: list[RubricLevelInput] = Field(default_factory=list, max_length=100)

    @field_validator("min_score", "max_score", "weight")
    @classmethod
    def numeric_values_must_be_finite(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("Rubric numeric values must be finite.")
        return value

    @model_validator(mode="after")
    def validate_score_range_and_levels(self) -> "RubricCriterionInput":
        if self.min_score >= self.max_score:
            raise ValueError("min_score must be less than max_score.")
        level_scores = [level.score for level in self.levels]
        if len(set(level_scores)) != len(level_scores):
            raise ValueError("Score levels must use unique score values.")
        if any(
            score < self.min_score or score > self.max_score
            for score in level_scores
        ):
            raise ValueError("Score levels must be within the criterion score range.")
        return self


class RubricCriteriaReplaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[RubricCriterionInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_criteria_set(self) -> "RubricCriteriaReplaceRequest":
        names = [criterion.name.casefold() for criterion in self.criteria]
        orders = [criterion.sort_order for criterion in self.criteria]
        if len(set(names)) != len(names):
            raise ValueError("Criterion names must be unique within a version.")
        if len(set(orders)) != len(orders):
            raise ValueError("Criterion sort orders must be unique.")

        total_weight = sum(
            (criterion.weight for criterion in self.criteria),
            start=Decimal("0"),
        )
        if abs(total_weight - WEIGHT_TOTAL) > WEIGHT_TOLERANCE:
            raise ValueError("Criterion weights must sum to 1.0.")
        return self


class RubricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: UUID
    created_by_id: UUID
    title: str
    description: str | None
    status: RubricStatus
    created_at: datetime


class RubricLevelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    score: Decimal
    description: str


class RubricCriterionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    rubric_version_id: UUID
    name: str
    description: str
    levels: list[RubricLevelResponse] = Field(validation_alias="levels_json")
    min_score: Decimal
    max_score: Decimal
    weight: Decimal
    sort_order: int


class RubricVersionResponse(BaseModel):
    id: UUID
    rubric_id: UUID
    version_number: int
    is_published: bool
    published_at: datetime | None
    snapshot: dict[str, object] | None
    criteria: list[RubricCriterionResponse]
