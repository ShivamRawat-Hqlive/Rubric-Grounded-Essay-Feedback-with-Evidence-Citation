"""Authenticated essay upload and text retrieval endpoints."""

import hashlib
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_roles
from app.core.config import Settings, get_settings
from app.db.models.course import CourseMemberRole
from app.db.models.essay import Essay, EssayChunk, EssayParseStatus
from app.db.models.user import User, UserRole
from app.db.session import get_db
from app.schemas.essay import EssayResponse, EssayTextResponse
from app.services.courses import has_course_membership
from app.services.documents.extractor import (
    EmptyDocumentError,
    InvalidDocumentError,
    UnsupportedDocumentError,
    UploadTooLargeError,
    validate_upload,
)
from app.services.documents.ocr import (
    OCRDependencyError,
    OCRPageRenderError,
    OCRUnreadableError,
    TrOCRProvider,
)
from app.services.documents.pipeline import ProcessedDocument, process_upload
from app.services.essays import get_accessible_essay, list_accessible_essays
from app.services.storage import LocalEssayStorage, StorageError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/essays", tags=["essays"])


def _storage(settings: Settings) -> LocalEssayStorage:
    return LocalEssayStorage(settings.resolved_file_storage_dir)


def _http_error_for_upload(exc: ValueError) -> HTTPException:
    if isinstance(exc, UploadTooLargeError):
        return HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The uploaded file exceeds the configured size limit.",
        )
    if isinstance(exc, UnsupportedDocumentError):
        return HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=str(exc),
    )


def _ocr_provider(settings: Settings):
    if not settings.ocr_enabled:
        return None
    if settings.ocr_provider.lower() != "trocr":
        raise OCRDependencyError(
            f"Unsupported OCR provider '{settings.ocr_provider}'. Use 'trocr'."
        )
    return TrOCRProvider(model_id=settings.ocr_model_id, device=settings.ocr_device)


def _persist_processed_essay(
    *,
    session: Session,
    current_user: User,
    course_id: UUID | None,
    document: ProcessedDocument,
    original_filename: str,
    content_type: str,
    data: bytes,
    storage: LocalEssayStorage,
) -> Essay:
    essay_id = uuid4()
    stored_path = storage.save(
        essay_id=essay_id,
        extension=Path(original_filename).suffix.lower(),
        data=data,
    )
    page_map = [asdict(page) for page in document.page_map]
    essay = Essay(
        id=essay_id,
        student_id=current_user.id,
        course_id=course_id,
        original_filename=original_filename,
        stored_path=stored_path,
        content_type=content_type,
        size_bytes=len(data),
        parse_status=EssayParseStatus.PARSED,
        extracted_text=document.extracted_text,
        normalized_text=document.normalized_text,
        normalizer_version=document.normalizer_version,
        offset_alignment=document.offset_alignment,
        page_map=page_map,
        extractor_name=document.extractor_name,
        extractor_version=document.extractor_version,
        sha256=hashlib.sha256(data).hexdigest(),
    )
    session.add(essay)
    session.add_all(
        EssayChunk(
            essay_id=essay_id,
            chunk_index=index,
            sentence_index=chunk.sentence_index,
            char_start=chunk.char_start,
            char_end=chunk.char_end,
            extracted_char_start=chunk.extracted_char_start,
            extracted_char_end=chunk.extracted_char_end,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            text=chunk.text,
        )
        for index, chunk in enumerate(document.chunks)
    )
    try:
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        try:
            storage.remove(stored_path)
        except StorageError:
            logger.exception(
                "Could not remove an essay upload after its database transaction failed.",
                extra={"essay_id": str(essay_id)},
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The essay could not be saved.",
        ) from exc
    session.refresh(essay)
    return essay


@router.post(
    "",
    response_model=EssayResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_essay(
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.STUDENT)),
    ],
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    file: Annotated[UploadFile, File()],
    course_id: Annotated[UUID | None, Form()] = None,
) -> Essay:
    try:
        data = await file.read(settings.max_upload_bytes + 1)
        upload = validate_upload(
            filename=file.filename,
            content_type=file.content_type,
            data=data,
            max_upload_bytes=settings.max_upload_bytes,
        )
        if course_id is not None and not has_course_membership(
            session,
            user=current_user,
            course_id=course_id,
            role=CourseMemberRole.STUDENT,
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found.",
            )
        document = process_upload(
            upload,
            max_extracted_characters=settings.max_extracted_chars,
            ocr_enabled=settings.ocr_enabled,
            ocr_provider=_ocr_provider(settings),
        )
    except (
        EmptyDocumentError,
        InvalidDocumentError,
        UnsupportedDocumentError,
        UploadTooLargeError,
        OCRDependencyError,
        OCRUnreadableError,
        OCRPageRenderError,
    ) as exc:
        raise _http_error_for_upload(exc) from exc
    finally:
        await file.close()

    try:
        return _persist_processed_essay(
            session=session,
            current_user=current_user,
            course_id=course_id,
            document=document,
            original_filename=upload.filename,
            content_type=upload.content_type,
            data=upload.data,
            storage=_storage(settings),
        )
    except StorageError as exc:
        logger.error(
            "Essay upload storage failed.",
            extra={"student_id": str(current_user.id)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Essay file storage is unavailable.",
        ) from exc


@router.get("", response_model=list[EssayResponse])
def list_essays(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> list[Essay]:
    return list_accessible_essays(session, user=current_user)


@router.get("/{essay_id}", response_model=EssayResponse)
def get_essay(
    essay_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> Essay:
    essay = get_accessible_essay(session, essay_id=essay_id, user=current_user)
    if essay is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Essay not found.",
        )
    return essay


@router.get("/{essay_id}/text", response_model=EssayTextResponse)
def get_essay_text(
    essay_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_db)],
) -> EssayTextResponse:
    essay = get_accessible_essay(session, essay_id=essay_id, user=current_user)
    if essay is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Essay not found.",
        )
    return EssayTextResponse(
        extracted_text=essay.extracted_text,
        normalized_text=essay.normalized_text,
        normalizer_version=essay.normalizer_version,
        offset_alignment=essay.offset_alignment,
        page_map=essay.page_map,
    )
