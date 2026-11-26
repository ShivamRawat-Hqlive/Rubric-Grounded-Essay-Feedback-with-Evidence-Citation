"""Course-scoped faculty evaluation review endpoints."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.evaluations import _evaluation_response
from app.db.models.course import CourseMemberRole, Enrollment
from app.db.models.evaluation import (
    CriterionScore,
    Evaluation,
    EvaluationReviewEvent,
    EvaluationStatus,
)
from app.db.models.essay import Essay
from app.db.models.rubric import RubricCriterion
from app.db.models.user import User, UserRole
from app.db.session import get_db
from app.schemas.evaluation import (
    CriterionScoreResponse,
    EvaluationResponse,
    EvaluationReviewEventResponse,
    FacultyCriterionUpdateRequest,
    FacultyReviewActionRequest,
    FacultyReviewNoteRequest,
    ReviewQueueItem,
)
from app.services.essays import get_accessible_essay

router = APIRouter(tags=["faculty reviews"])

EDITABLE_REVIEW_STATUSES = {
    EvaluationStatus.NEEDS_REVIEW,
    EvaluationStatus.CHANGES_REQUESTED,
}


def _get_faculty_evaluation(
    session: Session,
    *,
    evaluation_id: UUID,
    faculty: User,
) -> Evaluation:
    evaluation = session.get(Evaluation, evaluation_id)
    if evaluation is None or get_accessible_essay(
        session,
        essay_id=evaluation.essay_id,
        user=faculty,
    ) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Evaluation not found.",
        )
    return evaluation


def _require_editable_review(evaluation: Evaluation) -> None:
    if evaluation.status not in EDITABLE_REVIEW_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This evaluation is no longer open for faculty review.",
        )


def _record_event(
    session: Session,
    *,
    evaluation_id: UUID,
    faculty_id: UUID,
    action: str,
    notes: str | None = None,
    criterion_score_id: UUID | None = None,
) -> EvaluationReviewEvent:
    event = EvaluationReviewEvent(
        id=uuid4(),
        evaluation_id=evaluation_id,
        faculty_id=faculty_id,
        criterion_score_id=criterion_score_id,
        action=action,
        notes=notes,
        created_at=datetime.now(timezone.utc),
    )
    session.add(event)
    return event


@router.get(
    "/reviews/queue",
    response_model=list[ReviewQueueItem],
)
def list_review_queue(
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.FACULTY)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> list[ReviewQueueItem]:
    rows = session.execute(
        select(Evaluation, Essay.course_id, Essay.student_id)
        .join(Essay, Essay.id == Evaluation.essay_id)
        .join(Enrollment, Enrollment.course_id == Essay.course_id)
        .where(
            Enrollment.user_id == current_user.id,
            Enrollment.role == CourseMemberRole.FACULTY,
            Evaluation.status.in_(EDITABLE_REVIEW_STATUSES),
        )
        .order_by(Evaluation.started_at.desc(), Evaluation.id)
    ).all()
    items: list[ReviewQueueItem] = []
    for evaluation, course_id, student_id in rows:
        if course_id is None:
            continue
        items.append(
            ReviewQueueItem(
                evaluation_id=evaluation.id,
                essay_id=evaluation.essay_id,
                student_id=student_id,
                course_id=course_id,
                rubric_version_id=evaluation.rubric_version_id,
                evaluation_mode=evaluation.evaluation_mode,
                status=evaluation.status,
                started_at=evaluation.started_at,
                completed_at=evaluation.completed_at,
            )
        )
    return items


@router.patch(
    "/evaluations/{evaluation_id}/criterion-scores/{score_id}",
    response_model=CriterionScoreResponse,
)
def update_criterion_score(
    evaluation_id: UUID,
    score_id: UUID,
    request: FacultyCriterionUpdateRequest,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.FACULTY)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> CriterionScoreResponse:
    evaluation = _get_faculty_evaluation(
        session,
        evaluation_id=evaluation_id,
        faculty=current_user,
    )
    _require_editable_review(evaluation)
    score = session.scalar(
        select(CriterionScore).where(
            CriterionScore.id == score_id,
            CriterionScore.evaluation_id == evaluation.id,
        )
    )
    if score is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Criterion score not found.",
        )

    criterion = session.scalar(
        select(RubricCriterion).where(
            RubricCriterion.id == score.criterion_id,
            RubricCriterion.rubric_version_id == evaluation.rubric_version_id,
        )
    )
    if criterion is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The evaluation criterion is inconsistent with its rubric version.",
        )
    if (
        "faculty_score" in request.model_fields_set
        and request.faculty_score is not None
        and not criterion.min_score <= request.faculty_score <= criterion.max_score
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "faculty_score must be within the criterion's configured "
                f"range [{criterion.min_score}, {criterion.max_score}]."
            ),
        )

    for field in request.model_fields_set:
        setattr(score, field, getattr(request, field))

    if "faculty_score" in request.model_fields_set:
        weighted_rows = session.execute(
            select(CriterionScore, RubricCriterion.weight)
            .join(
                RubricCriterion,
                RubricCriterion.id == CriterionScore.criterion_id,
            )
            .where(CriterionScore.evaluation_id == evaluation.id)
        ).all()
        has_score_override = any(
            row.faculty_score is not None for row, _ in weighted_rows
        )
        evaluation.faculty_total_score = (
            sum(
                (
                    row.faculty_score
                    if row.faculty_score is not None
                    else row.ai_score
                )
                * weight
                for row, weight in weighted_rows
            )
            if has_score_override
            else None
        )

    _record_event(
        session,
        evaluation_id=evaluation.id,
        faculty_id=current_user.id,
        action="criterion_updated",
        criterion_score_id=score.id,
    )
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The faculty review update could not be saved.",
        ) from exc
    session.refresh(score)
    return CriterionScoreResponse.model_validate(score)


@router.post(
    "/evaluations/{evaluation_id}/review-notes",
    response_model=EvaluationReviewEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_review_note(
    evaluation_id: UUID,
    request: FacultyReviewNoteRequest,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.FACULTY)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> EvaluationReviewEventResponse:
    evaluation = _get_faculty_evaluation(
        session,
        evaluation_id=evaluation_id,
        faculty=current_user,
    )
    _require_editable_review(evaluation)
    event = _record_event(
        session,
        evaluation_id=evaluation.id,
        faculty_id=current_user.id,
        action="note_added",
        notes=request.notes,
    )
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The faculty review note could not be saved.",
        ) from exc
    session.refresh(event)
    return EvaluationReviewEventResponse.model_validate(event)


@router.post(
    "/evaluations/{evaluation_id}/review",
    response_model=EvaluationResponse,
)
def review_evaluation(
    evaluation_id: UUID,
    request: FacultyReviewActionRequest,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.FACULTY)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> EvaluationResponse:
    evaluation = _get_faculty_evaluation(
        session,
        evaluation_id=evaluation_id,
        faculty=current_user,
    )
    _require_editable_review(evaluation)
    evaluation.status = EvaluationStatus(request.action)
    _record_event(
        session,
        evaluation_id=evaluation.id,
        faculty_id=current_user.id,
        action=request.action,
        notes=request.notes,
    )
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The faculty review decision could not be saved.",
        ) from exc
    session.refresh(evaluation)
    return _evaluation_response(
        session,
        evaluation,
        redact_ai_results=False,
        include_review_history=True,
    )
