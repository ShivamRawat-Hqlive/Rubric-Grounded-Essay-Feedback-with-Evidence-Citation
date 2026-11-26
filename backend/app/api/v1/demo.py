"""Unauthenticated, in-memory workflows for the explicitly local portfolio demo."""

from threading import RLock

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.config import Settings, get_settings
from app.schemas.demo import DemoEvaluationResponse, DemoReviewRequest
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
from app.services.documents.pipeline import process_upload
from app.services.demo_evaluation import create_demo_evaluation, verify_demo_citations

router = APIRouter(prefix="/demo", tags=["local-demo"])
_evaluations: dict[str, dict[str, object]] = {}
_evaluations_lock = RLock()


def _upload_error(exc: ValueError) -> HTTPException:
    if isinstance(exc, UploadTooLargeError):
        return HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="The essay exceeds the configured upload limit.",
        )
    if isinstance(exc, UnsupportedDocumentError):
        return HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=str(exc),
        )
    if isinstance(exc, OCRDependencyError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    if isinstance(exc, OCRPageRenderError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )
    if isinstance(exc, (EmptyDocumentError, OCRUnreadableError, InvalidDocumentError)):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=str(exc),
    )


def _get_evaluation(evaluation_id: str) -> dict[str, object]:
    with _evaluations_lock:
        evaluation = _evaluations.get(evaluation_id)
        if evaluation is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Demo evaluation not found.",
            )
        return evaluation


@router.post(
    "/evaluations",
    response_model=DemoEvaluationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_and_evaluate_demo_essay(
    file: UploadFile = File(),
) -> DemoEvaluationResponse:
    settings: Settings = get_settings()
    try:
        data = await file.read(settings.max_upload_bytes + 1)
        is_docx = (
            file.filename is not None
            and file.filename.replace("\\", "/").rsplit("/", 1)[-1].lower().endswith(".docx")
        )
        if is_docx:
            raise UnsupportedDocumentError(
                "The local demo accepts PDF and plain-text TXT essays."
            )
        upload = validate_upload(
            filename=file.filename,
            content_type=file.content_type,
            data=data,
            max_upload_bytes=settings.max_upload_bytes,
        )
        if upload.extension not in (".pdf", ".txt"):
            raise UnsupportedDocumentError(
                "The local demo accepts PDF and plain-text TXT essays."
            )
        provider = (
            TrOCRProvider(model_id=settings.ocr_model_id, device=settings.ocr_device)
            if settings.ocr_enabled
            else None
        )
        document = process_upload(
            upload,
            max_extracted_characters=settings.max_extracted_chars,
            ocr_enabled=settings.ocr_enabled,
            ocr_provider=provider,
        )
        evaluation = create_demo_evaluation(document, filename=upload.filename)
        if not verify_demo_citations(evaluation):
            raise RuntimeError("The demo evaluator produced an invalid evidence citation.")
    except (
        EmptyDocumentError,
        InvalidDocumentError,
        UnsupportedDocumentError,
        UploadTooLargeError,
        OCRDependencyError,
        OCRPageRenderError,
        OCRUnreadableError,
    ) as exc:
        raise _upload_error(exc) from exc
    finally:
        await file.close()

    with _evaluations_lock:
        _evaluations[str(evaluation["id"])] = evaluation
    return DemoEvaluationResponse.model_validate(evaluation)


@router.get(
    "/evaluations",
    response_model=list[DemoEvaluationResponse],
)
def list_demo_evaluations() -> list[DemoEvaluationResponse]:
    with _evaluations_lock:
        evaluations = sorted(
            _evaluations.values(),
            key=lambda item: str(item["created_at"]),
            reverse=True,
        )
        return [DemoEvaluationResponse.model_validate(item) for item in evaluations]


@router.get(
    "/evaluations/{evaluation_id}",
    response_model=DemoEvaluationResponse,
)
def get_demo_evaluation(evaluation_id: str) -> DemoEvaluationResponse:
    return DemoEvaluationResponse.model_validate(_get_evaluation(evaluation_id))


@router.post(
    "/evaluations/{evaluation_id}/review",
    response_model=DemoEvaluationResponse,
)
def review_demo_evaluation(
    evaluation_id: str,
    request: DemoReviewRequest,
) -> DemoEvaluationResponse:
    evaluation = _get_evaluation(evaluation_id)
    if evaluation["status"] == "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This demo evaluation is already approved.",
        )
    with _evaluations_lock:
        evaluation["status"] = request.action
        evaluation["faculty_note"] = request.note.strip() if request.note else None
    return DemoEvaluationResponse.model_validate(evaluation)
