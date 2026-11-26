"""Authorized synchronous AI essay evaluation endpoints."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import Settings, get_settings
from app.db.models.course import CourseMemberRole, Enrollment
from app.db.models.evaluation import (
    CriterionScore,
    Evaluation,
    EvaluationReviewEvent,
    EvaluationStatus,
)
from app.db.models.essay import Essay, EssayChunk, EssayParseStatus
from app.db.models.rubric import (
    RubricCriterion,
    RubricStatus,
)
from app.db.models.user import User, UserRole
from app.db.session import get_db
from app.schemas.evaluation import (
    CriterionScoreResponse,
    EvaluationReviewEventResponse,
    EvaluationCreateRequest,
    EvaluationResponse,
)
from app.schemas.rubric import RubricCriteriaReplaceRequest
from app.services.essays import get_accessible_essay
from app.services.evidence import EvidenceIntegrityError
from app.services.llm.base import (
    InvalidLLMEvidenceError,
    InvalidLLMOutputError,
    InvalidLLMScoreError,
    LLMConfigurationError,
    LLMProviderError,
    LLMTimeoutError,
)
from app.services.llm.evaluation import EvaluationEngine
from app.services.llm.factory import create_llm_provider
from app.services.rubrics import get_accessible_rubric_version

logger = logging.getLogger(__name__)
router = APIRouter(tags=["evaluations"])


def _validate_rubric_criteria(criteria: list[RubricCriterion]) -> None:
    try:
        RubricCriteriaReplaceRequest.model_validate(
            {
                "criteria": [
                    {
                        "name": item.name,
                        "description": item.description,
                        "min_score": item.min_score,
                        "max_score": item.max_score,
                        "weight": item.weight,
                        "sort_order": item.sort_order,
                        "levels": item.levels_json,
                    }
                    for item in criteria
                ]
            }
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The published rubric criteria are invalid.",
        ) from exc


def _safe_failure(
    session: Session,
    evaluation: Evaluation,
    *,
    code: str,
) -> None:
    evaluation.status = EvaluationStatus.FAILED
    evaluation.error_code = code
    evaluation.completed_at = datetime.now(timezone.utc)
    session.commit()


def _evaluation_response(
    session: Session,
    evaluation: Evaluation,
    *,
    redact_ai_results: bool,
    include_review_history: bool = False,
) -> EvaluationResponse:
    criterion_scores: list[CriterionScoreResponse] = []
    review_history: list[EvaluationReviewEventResponse] = []
    if not redact_ai_results:
        rows = session.scalars(
            select(CriterionScore)
            .join(
                RubricCriterion,
                RubricCriterion.id == CriterionScore.criterion_id,
            )
            .where(CriterionScore.evaluation_id == evaluation.id)
            .order_by(RubricCriterion.sort_order)
        )
        criterion_scores = [
            CriterionScoreResponse.model_validate(row) for row in rows
        ]
    if include_review_history:
        events = session.scalars(
            select(EvaluationReviewEvent)
            .where(EvaluationReviewEvent.evaluation_id == evaluation.id)
            .order_by(
                EvaluationReviewEvent.created_at,
                EvaluationReviewEvent.id,
            )
        )
        review_history = [
            EvaluationReviewEventResponse.model_validate(event)
            for event in events
        ]
    return EvaluationResponse(
        id=evaluation.id,
        essay_id=evaluation.essay_id,
        rubric_version_id=evaluation.rubric_version_id,
        requested_by_id=evaluation.requested_by_id,
        status=evaluation.status,
        evaluation_mode=evaluation.evaluation_mode,
        ai_total_score=None if redact_ai_results else evaluation.ai_total_score,
        faculty_total_score=(
            None if redact_ai_results else evaluation.faculty_total_score
        ),
        has_unsupported_flags=False if redact_ai_results else evaluation.has_unsupported_flags,
        error_code=None if redact_ai_results else evaluation.error_code,
        started_at=evaluation.started_at,
        completed_at=evaluation.completed_at,
        criterion_scores=criterion_scores,
        review_history=review_history,
    )


def _error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


_LLM_PROVIDER_MESSAGES = {
    "OPENAI_AUTHENTICATION_ERROR": (
        "OpenAI rejected the configured API key. Verify it is active and belongs "
        "to the intended project."
    ),
    "OPENAI_QUOTA_EXCEEDED": (
        "The OpenAI account or project has no available API quota. Check billing "
        "and usage limits."
    ),
    "OPENAI_MODEL_NOT_FOUND": (
        "The configured OpenAI model was not found or is unavailable to this project."
    ),
    "OPENAI_PERMISSION_ERROR": (
        "The configured OpenAI key does not have permission for this request."
    ),
    "OPENAI_INVALID_REQUEST": (
        "OpenAI rejected the request. Check the configured model and structured-output compatibility."
    ),
    "OPENAI_RATE_LIMIT": (
        "OpenAI rate-limited the request. Wait briefly and try again."
    ),
    "OPENAI_CONNECTION_ERROR": (
        "The backend could not connect to OpenAI. Check network access and try again."
    ),
    "OPENAI_SERVER_ERROR": (
        "OpenAI returned a temporary server error. Try again shortly."
    ),
    "OPENAI_MALFORMED_RESPONSE": (
        "OpenAI returned a malformed response. Try again; if it continues, contact an administrator."
    ),
    "OPENAI_EMPTY_RESPONSE": (
        "OpenAI returned an empty response. Try the evaluation again."
    ),
    "OPENAI_REFUSAL": (
        "OpenAI declined the evaluation request. Contact an administrator if this persists."
    ),
    "OPENAI_PROVIDER_ERROR": (
        "OpenAI could not complete the request. Check backend diagnostics."
    ),
    "LLM_PROVIDER_ERROR": (
        "The configured LLM provider could not complete the evaluation."
    ),
}


@router.post(
    "/essays/{essay_id}/evaluations",
    response_model=EvaluationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_evaluation(
    essay_id: UUID,
    request: EvaluationCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EvaluationResponse:
    essay = get_accessible_essay(
        session,
        essay_id=essay_id,
        user=current_user,
    )
    if essay is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Essay not found.")
    if (
        essay.parse_status is not EssayParseStatus.PARSED
        or not essay.normalized_text.strip()
        or not essay.offset_alignment
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The essay is not ready for evaluation.",
        )
    if len(essay.normalized_text) > settings.max_evaluation_chars:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The essay exceeds the configured evaluation text limit.",
        )

    rubric_access = get_accessible_rubric_version(
        session,
        version_id=request.rubric_version_id,
        user=current_user,
    )
    if rubric_access is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Published rubric version not found.",
        )
    rubric, rubric_version = rubric_access
    if (
        rubric.status is not RubricStatus.PUBLISHED
        or not rubric_version.is_published
        or essay.course_id is None
        or essay.course_id != rubric.course_id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The essay and published rubric must belong to the same course.",
        )

    criteria = list(
        session.scalars(
            select(RubricCriterion)
            .where(RubricCriterion.rubric_version_id == rubric_version.id)
            .order_by(RubricCriterion.sort_order)
        )
    )
    if not criteria:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The published rubric version has no criteria.",
        )
    _validate_rubric_criteria(criteria)
    essay_chunks = list(
        session.scalars(
            select(EssayChunk)
            .where(EssayChunk.essay_id == essay.id)
            .order_by(EssayChunk.chunk_index)
        )
    )
    if not essay_chunks:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The essay has no passages available for evaluation.",
        )

    try:
        provider = create_llm_provider(settings)
    except LLMConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_error_detail(
                "LLM_NOT_CONFIGURED",
                "Configure LLM_PROVIDER=openai and OPENAI_API_KEY before evaluating.",
            ),
        ) from exc

    evaluation = Evaluation(
        id=uuid4(),
        essay_id=essay.id,
        rubric_version_id=rubric_version.id,
        requested_by_id=current_user.id,
        status=EvaluationStatus.RUNNING,
        evaluation_mode=(
            "mock" if settings.llm_provider == "mock" else "openai"
        ),
    )
    session.add(evaluation)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        await provider.aclose()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An evaluation for this essay and rubric version is already running.",
        ) from exc

    try:
        result = await EvaluationEngine(provider).evaluate(
            essay=essay,
            essay_chunks=essay_chunks,
            rubric=rubric,
            rubric_version=rubric_version,
            criteria=criteria,
        )
    except LLMTimeoutError as exc:
        _safe_failure(session, evaluation, code="LLM_TIMEOUT")
        logger.warning(
            "Essay evaluation failed.",
            extra={"evaluation_id": str(evaluation.id), "error_code": "LLM_TIMEOUT"},
        )
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=_error_detail("LLM_TIMEOUT", "The configured LLM provider timed out."),
        ) from exc
    except InvalidLLMScoreError as exc:
        _safe_failure(session, evaluation, code="INVALID_SCORE")
        logger.warning(
            "Essay evaluation failed.",
            extra={"evaluation_id": str(evaluation.id), "error_code": "INVALID_SCORE"},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail(
                "INVALID_SCORE",
                "The LLM provider returned scores outside the rubric's allowed ranges.",
            ),
        ) from exc
    except InvalidLLMOutputError as exc:
        _safe_failure(session, evaluation, code="INVALID_PROVIDER_OUTPUT")
        logger.warning(
            "Essay evaluation failed.",
            extra={
                "evaluation_id": str(evaluation.id),
                "error_code": "INVALID_PROVIDER_OUTPUT",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail(
                "INVALID_PROVIDER_OUTPUT",
                "The LLM provider did not return valid structured evaluation data.",
            ),
        ) from exc
    except InvalidLLMEvidenceError as exc:
        _safe_failure(session, evaluation, code="INVALID_EVIDENCE")
        logger.warning(
            "Essay evaluation failed.",
            extra={
                "evaluation_id": str(evaluation.id),
                "error_code": "INVALID_EVIDENCE",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail(
                "INVALID_EVIDENCE",
                "The LLM provider returned evidence that could not be verified.",
            ),
        ) from exc
    except EvidenceIntegrityError as exc:
        _safe_failure(session, evaluation, code="ESSAY_DATA_INVALID")
        logger.error(
            "Essay evaluation source data failed integrity checks.",
            extra={
                "evaluation_id": str(evaluation.id),
                "error_code": "ESSAY_DATA_INVALID",
            },
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_error_detail(
                "ESSAY_DATA_INVALID",
                "The essay passage data is inconsistent and cannot be evaluated.",
            ),
        ) from exc
    except LLMProviderError as exc:
        error_code = exc.error_code or "LLM_PROVIDER_ERROR"
        _safe_failure(session, evaluation, code=error_code)
        logger.warning(
            "Essay evaluation failed.",
            extra={
                "evaluation_id": str(evaluation.id),
                "error_code": error_code,
                "provider_exception_type": exc.exception_type or type(exc).__name__,
                "provider_http_status": exc.http_status,
                "provider_error_code": exc.provider_error_code,
                "provider_message": exc.provider_message,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=_error_detail(
                error_code,
                _LLM_PROVIDER_MESSAGES.get(
                    error_code,
                    "The LLM provider could not complete the evaluation. Check backend diagnostics.",
                ),
            ),
        ) from exc
    except asyncio.CancelledError:
        _safe_failure(session, evaluation, code="REQUEST_CANCELLED")
        raise
    finally:
        await provider.aclose()

    evaluation.status = EvaluationStatus.NEEDS_REVIEW
    evaluation.ai_total_score = result.total_score
    evaluation.has_unsupported_flags = result.has_unsupported_flags
    evaluation.completed_at = datetime.now(timezone.utc)
    session.add_all(
        CriterionScore(
            evaluation_id=evaluation.id,
            rubric_version_id=rubric_version.id,
            criterion_id=criterion_result.criterion_id,
            ai_score=criterion_result.score,
            ai_rationale=criterion_result.rationale,
            strengths=criterion_result.strengths,
            weaknesses=criterion_result.weaknesses,
            suggestions=criterion_result.suggestions,
            claims=[claim.as_json() for claim in criterion_result.claims],
        )
        for criterion_result in result.criterion_results
    )
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The evaluation result could not be saved.",
        ) from exc
    session.refresh(evaluation)
    return _evaluation_response(
        session,
        evaluation,
        redact_ai_results=current_user.role is UserRole.STUDENT,
    )


@router.get(
    "/evaluations",
    response_model=list[EvaluationResponse],
)
def list_evaluations(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
    essay_id: UUID | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[EvaluationResponse]:
    statement = (
        select(Evaluation)
        .join(Essay, Essay.id == Evaluation.essay_id)
        .order_by(Evaluation.started_at.desc(), Evaluation.id)
    )
    if current_user.role is UserRole.STUDENT:
        statement = statement.where(Essay.student_id == current_user.id)
    elif current_user.role is UserRole.FACULTY:
        statement = (
            statement.join(Enrollment, Enrollment.course_id == Essay.course_id)
            .where(
                Enrollment.user_id == current_user.id,
                Enrollment.role == CourseMemberRole.FACULTY,
            )
            .distinct()
        )
    if essay_id is not None:
        statement = statement.where(Evaluation.essay_id == essay_id)

    evaluations = session.scalars(
        statement.limit(limit).offset(offset)
    ).all()
    return [
        _evaluation_response(
            session,
            evaluation,
            redact_ai_results=(
                current_user.role is UserRole.STUDENT
                and evaluation.status is not EvaluationStatus.APPROVED
            ),
            include_review_history=current_user.role in (
                UserRole.FACULTY,
                UserRole.ADMIN,
            ),
        )
        for evaluation in evaluations
    ]


@router.get(
    "/evaluations/{evaluation_id}",
    response_model=EvaluationResponse,
)
def get_evaluation(
    evaluation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> EvaluationResponse:
    evaluation = session.get(Evaluation, evaluation_id)
    if evaluation is None or get_accessible_essay(
        session,
        essay_id=evaluation.essay_id,
        user=current_user,
    ) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation not found.")
    return _evaluation_response(
        session,
        evaluation,
        redact_ai_results=(
            current_user.role is UserRole.STUDENT
            and evaluation.status is not EvaluationStatus.APPROVED
        ),
        include_review_history=current_user.role in (
            UserRole.FACULTY,
            UserRole.ADMIN,
        ),
    )
