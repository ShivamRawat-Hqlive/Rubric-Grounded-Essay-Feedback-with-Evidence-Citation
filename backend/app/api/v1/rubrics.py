"""Course-scoped rubric authoring, versioning, and publication endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.db.models.course import Course, CourseMemberRole
from app.db.models.rubric import (
    Rubric,
    RubricCriterion,
    RubricStatus,
    RubricVersion,
)
from app.db.models.user import User, UserRole
from app.db.session import get_db
from app.schemas.rubric import (
    RubricCreateRequest,
    RubricCriteriaReplaceRequest,
    RubricCriterionInput,
    RubricCriterionResponse,
    RubricPatchRequest,
    RubricResponse,
    RubricVersionResponse,
    WEIGHT_TOLERANCE,
    WEIGHT_TOTAL,
)
from app.services.courses import has_course_membership
from app.services.rubrics import (
    get_accessible_rubric,
    get_accessible_rubric_version,
    get_accessible_rubric_versions,
    get_owned_rubric,
    get_owned_rubric_version,
    list_accessible_rubrics,
)

router = APIRouter(tags=["rubrics"])


def _rubric_or_404(
    session: Session,
    *,
    rubric_id: UUID,
    user: User,
) -> Rubric:
    rubric = get_accessible_rubric(session, rubric_id=rubric_id, user=user)
    if rubric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rubric not found.",
        )
    return rubric


def _owned_rubric_or_404(
    session: Session,
    *,
    rubric_id: UUID,
    user: User,
    lock: bool = False,
) -> Rubric:
    rubric = get_owned_rubric(
        session,
        rubric_id=rubric_id,
        user=user,
        lock=lock,
    )
    if rubric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rubric not found.",
        )
    return rubric


def _owned_version_or_404(
    session: Session,
    *,
    version_id: UUID,
    user: User,
    lock: bool = False,
) -> tuple[Rubric, RubricVersion]:
    result = get_owned_rubric_version(
        session,
        version_id=version_id,
        user=user,
        lock=lock,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rubric version not found.",
        )
    return result


def _version_response(
    session: Session,
    version: RubricVersion,
) -> RubricVersionResponse:
    criteria = session.scalars(
        select(RubricCriterion)
        .where(RubricCriterion.rubric_version_id == version.id)
        .order_by(RubricCriterion.sort_order)
    ).all()
    return RubricVersionResponse(
        id=version.id,
        rubric_id=version.rubric_id,
        version_number=version.version_number,
        is_published=version.is_published,
        published_at=version.published_at,
        snapshot=version.snapshot,
        criteria=[
            RubricCriterionResponse.model_validate(criterion)
            for criterion in criteria
        ],
    )


def _criterion_record(
    criterion: RubricCriterionInput,
    *,
    version_id: UUID,
) -> RubricCriterion:
    return RubricCriterion(
        id=uuid4(),
        rubric_version_id=version_id,
        name=criterion.name,
        description=criterion.description,
        levels_json=[
            {"score": str(level.score), "description": level.description}
            for level in criterion.levels
        ],
        min_score=criterion.min_score,
        max_score=criterion.max_score,
        weight=criterion.weight,
        sort_order=criterion.sort_order,
    )


def _validate_persisted_criteria(
    criteria: list[RubricCriterion],
) -> list[RubricCriterionInput]:
    try:
        request = RubricCriteriaReplaceRequest.model_validate(
            {
                "criteria": [
                    {
                        "name": criterion.name,
                        "description": criterion.description,
                        "levels": criterion.levels_json,
                        "min_score": criterion.min_score,
                        "max_score": criterion.max_score,
                        "weight": criterion.weight,
                        "sort_order": criterion.sort_order,
                    }
                    for criterion in criteria
                ]
            }
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The rubric version does not satisfy scoring constraints.",
        ) from exc
    return request.criteria


def _published_snapshot(
    rubric: Rubric,
    version: RubricVersion,
    stored_criteria: list[RubricCriterion],
    criteria: list[RubricCriterionInput],
) -> dict[str, object]:
    return {
        "rubric": {
            "id": str(rubric.id),
            "course_id": str(rubric.course_id),
            "title": rubric.title,
            "description": rubric.description,
        },
        "version_number": version.version_number,
        "criteria": [
            {
                "id": str(stored_criterion.id),
                "name": criterion.name,
                "description": criterion.description,
                "min_score": str(criterion.min_score),
                "max_score": str(criterion.max_score),
                "weight": str(criterion.weight),
                "sort_order": criterion.sort_order,
                "levels": [
                    {"score": str(level.score), "description": level.description}
                    for level in criterion.levels
                ],
            }
            for stored_criterion, criterion in zip(stored_criteria, criteria)
        ],
    }


def _commit_or_conflict(session: Session, *, detail: str) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        ) from exc


@router.post(
    "/rubrics",
    response_model=RubricResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_rubric(
    request: RubricCreateRequest,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.FACULTY)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> Rubric:
    course = session.get(Course, request.course_id)
    if (
        course is None
        or not course.is_active
        or not has_course_membership(
            session,
            user=current_user,
            course_id=request.course_id,
            role=CourseMemberRole.FACULTY,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Course not found.",
        )

    rubric = Rubric(
        id=uuid4(),
        course_id=course.id,
        created_by_id=current_user.id,
        title=request.title,
        description=request.description,
        status=RubricStatus.DRAFT,
    )
    session.add(rubric)
    session.add(
        RubricVersion(
            id=uuid4(),
            rubric_id=rubric.id,
            version_number=1,
        )
    )
    _commit_or_conflict(session, detail="The rubric could not be created.")
    session.refresh(rubric)
    return rubric


@router.get("/rubrics", response_model=list[RubricResponse])
def list_rubrics(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> list[Rubric]:
    return list_accessible_rubrics(session, user=current_user)


@router.get("/rubrics/{rubric_id}", response_model=RubricResponse)
def get_rubric(
    rubric_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> Rubric:
    return _rubric_or_404(session, rubric_id=rubric_id, user=current_user)


@router.patch("/rubrics/{rubric_id}", response_model=RubricResponse)
def update_rubric(
    rubric_id: UUID,
    request: RubricPatchRequest,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.FACULTY)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> Rubric:
    rubric = _owned_rubric_or_404(
        session,
        rubric_id=rubric_id,
        user=current_user,
        lock=True,
    )
    if rubric.status is not RubricStatus.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft rubric metadata can be edited.",
        )
    for field, value in request.model_dump(exclude_unset=True).items():
        setattr(rubric, field, value)
    _commit_or_conflict(session, detail="The rubric could not be updated.")
    session.refresh(rubric)
    return rubric


@router.post(
    "/rubrics/{rubric_id}/versions",
    response_model=RubricVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_rubric_version(
    rubric_id: UUID,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.FACULTY)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> RubricVersionResponse:
    rubric = _owned_rubric_or_404(
        session,
        rubric_id=rubric_id,
        user=current_user,
        lock=True,
    )
    if rubric.status is RubricStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Archived rubrics cannot receive new versions.",
        )

    previous = session.scalar(
        select(RubricVersion)
        .where(RubricVersion.rubric_id == rubric.id)
        .order_by(RubricVersion.version_number.desc())
        .limit(1)
        .with_for_update()
    )
    if previous is not None and not previous.is_published:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Publish or archive the current draft version first.",
        )

    version_number = previous.version_number + 1 if previous else 1
    version = RubricVersion(
        id=uuid4(),
        rubric_id=rubric.id,
        version_number=version_number,
    )
    session.add(version)
    if previous is not None:
        previous_criteria = session.scalars(
            select(RubricCriterion)
            .where(RubricCriterion.rubric_version_id == previous.id)
            .order_by(RubricCriterion.sort_order)
        ).all()
        session.add_all(
            RubricCriterion(
                id=uuid4(),
                rubric_version_id=version.id,
                name=criterion.name,
                description=criterion.description,
                levels_json=[dict(level) for level in criterion.levels_json],
                min_score=criterion.min_score,
                max_score=criterion.max_score,
                weight=criterion.weight,
                sort_order=criterion.sort_order,
            )
            for criterion in previous_criteria
        )

    _commit_or_conflict(session, detail="The rubric version could not be created.")
    return _version_response(session, version)


@router.get(
    "/rubrics/{rubric_id}/versions",
    response_model=list[RubricVersionResponse],
)
def list_rubric_versions(
    rubric_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> list[RubricVersionResponse]:
    rubric = _rubric_or_404(session, rubric_id=rubric_id, user=current_user)
    versions = get_accessible_rubric_versions(
        session,
        rubric=rubric,
        user=current_user,
    )
    return [_version_response(session, version) for version in versions]


@router.get(
    "/rubric-versions/{version_id}",
    response_model=RubricVersionResponse,
)
def get_rubric_version(
    version_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> RubricVersionResponse:
    result = get_accessible_rubric_version(
        session,
        version_id=version_id,
        user=current_user,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rubric version not found.",
        )
    _, version = result
    return _version_response(session, version)


@router.put(
    "/rubric-versions/{version_id}/criteria",
    response_model=RubricVersionResponse,
)
def replace_rubric_criteria(
    version_id: UUID,
    request: RubricCriteriaReplaceRequest,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.FACULTY)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> RubricVersionResponse:
    rubric, version = _owned_version_or_404(
        session,
        version_id=version_id,
        user=current_user,
        lock=True,
    )
    if rubric.status is RubricStatus.ARCHIVED or version.is_published:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only criteria in an unpublished version can be edited.",
        )

    session.execute(
        delete(RubricCriterion).where(
            RubricCriterion.rubric_version_id == version.id
        )
    )
    session.add_all(
        _criterion_record(criterion, version_id=version.id)
        for criterion in request.criteria
    )
    _commit_or_conflict(session, detail="The rubric criteria could not be saved.")
    return _version_response(session, version)


@router.post(
    "/rubric-versions/{version_id}/publish",
    response_model=RubricVersionResponse,
)
def publish_rubric_version(
    version_id: UUID,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.FACULTY)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> RubricVersionResponse:
    rubric, version = _owned_version_or_404(
        session,
        version_id=version_id,
        user=current_user,
        lock=True,
    )
    if rubric.status is RubricStatus.ARCHIVED or version.is_published:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This rubric version cannot be published.",
        )

    stored_criteria = session.scalars(
        select(RubricCriterion)
        .where(RubricCriterion.rubric_version_id == version.id)
        .order_by(RubricCriterion.sort_order)
    ).all()
    if not stored_criteria:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A rubric version requires at least one criterion to publish.",
        )
    criteria = _validate_persisted_criteria(stored_criteria)
    total_weight = sum(
        (criterion.weight for criterion in criteria),
        start=Decimal("0"),
    )
    if abs(total_weight - WEIGHT_TOTAL) > WEIGHT_TOLERANCE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Criterion weights must sum to 1.0.",
        )

    version.snapshot = _published_snapshot(
        rubric,
        version,
        stored_criteria,
        criteria,
    )
    version.is_published = True
    version.published_at = datetime.now(timezone.utc)
    rubric.status = RubricStatus.PUBLISHED
    _commit_or_conflict(session, detail="The rubric version could not be published.")
    return _version_response(session, version)


@router.post("/rubrics/{rubric_id}/archive", response_model=RubricResponse)
def archive_rubric(
    rubric_id: UUID,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.FACULTY)),
    ],
    session: Annotated[Session, Depends(get_db)],
) -> Rubric:
    rubric = _owned_rubric_or_404(
        session,
        rubric_id=rubric_id,
        user=current_user,
        lock=True,
    )
    if rubric.status is RubricStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The rubric is already archived.",
        )
    rubric.status = RubricStatus.ARCHIVED
    _commit_or_conflict(session, detail="The rubric could not be archived.")
    session.refresh(rubric)
    return rubric
