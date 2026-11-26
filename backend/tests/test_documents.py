"""Document validation, extraction, offsets, and upload API tests."""

from io import BytesIO
from pathlib import Path
import zipfile
from uuid import UUID

import pymupdf
import pytest
from docx import Document
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.security import create_access_token
from app.core.upload_limits import UploadRequestSizeLimitMiddleware
from app.db.models.course import CourseMemberRole, Enrollment
from app.db.models.essay import Essay, EssayChunk
from app.db.models.user import User, UserRole
from app.services.auth import create_user
from app.services.documents.alignment import map_normalized_span
from app.services.documents.extractor import (
    EmptyDocumentError,
    InvalidDocumentError,
    UnsupportedDocumentError,
    UploadTooLargeError,
    extract_document,
    validate_upload,
)
from app.services.documents.pipeline import process_upload
from app.services.documents.preprocessor import normalize_text
from app.services.storage import LocalEssayStorage, StorageError
from app.services.documents.ocr import (
    OCRDependencyError,
    OCRPageRenderError,
    OCRProvider,
    OCRUnreadableError,
    OCRPageResult,
)


def _pdf_bytes(pages: list[str]) -> bytes:
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def _image_pdf_bytes(page_count: int = 1) -> bytes:
    document = pymupdf.open()
    for _ in range(page_count):
        page = document.new_page(width=200, height=200)
        pixmap = pymupdf.Pixmap(
            pymupdf.csRGB,
            200,
            200,
            b"\xff" * (200 * 200 * 3),
            False,
        )
        page.insert_image(page.rect, pixmap=pixmap)
    data = document.tobytes()
    document.close()
    return data


class MockOCRProvider:
    def __init__(self, results: list[str] | None = None):
        self.results = results or []
        self.calls = 0

    def recognize_page(self, image_bytes: bytes) -> OCRPageResult:
        self.calls += 1
        if not self.results:
            return OCRPageResult(text="")
        return OCRPageResult(text=self.results.pop(0))


def _docx_bytes() -> bytes:
    document = Document()
    document.add_paragraph("First DOCX paragraph.")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Table evidence"
    table.cell(0, 1).text = "Second cell"
    stream = BytesIO()
    document.save(stream)
    return stream.getvalue()


def _token(user_id: UUID, settings: Settings) -> str:
    return create_access_token(
        user_id,
        settings.jwt_secret_key.get_secret_value(),
        settings.jwt_access_token_expire_minutes,
    )


def _create_user(
    session_factory: sessionmaker,
    *,
    email: str,
    role: UserRole,
) -> User:
    with session_factory() as session:
        user = create_user(
            session,
            email=email,
            password="correct horse battery staple",
            full_name=email.split("@", 1)[0],
            role=role,
        )
        return user


def test_txt_normalization_keeps_offsets_reversible() -> None:
    source = "Cafe\u0301\t  \r\n\u201cEvidence\u201d \u2014 matters."
    normalized, alignment = normalize_text(source)

    assert normalized == 'Caf\u00e9 \n"Evidence" - matters.'
    start = normalized.index("\u00e9")
    assert map_normalized_span(alignment, start, start + 1) == (3, 5)
    assert normalize_text(source) == (normalized, alignment)


def test_txt_extraction_decodes_utf8_and_preserves_document_offsets() -> None:
    upload = validate_upload(
        filename="essay.txt",
        content_type="text/plain",
        data=b"\xef\xbb\xbfFirst line.\r\nSecond line.",
        max_upload_bytes=1024,
    )
    extracted = extract_document(upload)

    assert extracted.text == "First line.\r\nSecond line."
    assert len(extracted.pages) == 1
    assert extracted.pages[0].page_number is None
    assert (extracted.pages[0].extracted_char_start, extracted.pages[0].extracted_char_end) == (
        0,
        len(extracted.text),
    )


def test_pdf_extraction_preserves_page_offsets_and_chunk_invariants() -> None:
    upload = validate_upload(
        filename="essay.PDF",
        content_type="application/pdf",
        data=_pdf_bytes(["First page evidence.", "Second page evidence."]),
        max_upload_bytes=1024 * 1024,
    )
    processed = process_upload(upload)

    assert len(processed.page_map) == 2
    assert [page.page_number for page in processed.page_map] == [1, 2]
    assert processed.extracted_text[processed.page_map[1].extracted_char_start :].startswith(
        "Second page evidence."
    )
    assert processed.page_map[1].normalized_char_start > processed.page_map[0].normalized_char_start
    for chunk in processed.chunks:
        assert processed.normalized_text[chunk.char_start : chunk.char_end] == chunk.text
        extracted_span = processed.extracted_text[
            chunk.extracted_char_start : chunk.extracted_char_end
        ]
        assert normalize_text(extracted_span)[0] == chunk.text
    assert any(chunk.page_start == 2 for chunk in processed.chunks)


def test_pdf_extraction_preserves_text_block_paragraph_boundaries() -> None:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "First paragraph.")
    page.insert_text((72, 120), "Second paragraph.")
    upload = validate_upload(
        filename="paragraphs.pdf",
        content_type="application/pdf",
        data=document.tobytes(),
        max_upload_bytes=1024 * 1024,
    )
    document.close()

    extracted = extract_document(upload)

    assert "First paragraph.\n\nSecond paragraph." in extracted.text
    assert extracted.extractor_version.endswith("-blocks-v1")


def test_image_only_pdf_requires_explicit_ocr() -> None:
    upload = validate_upload(
        filename="scanned.pdf",
        content_type="application/pdf",
        data=_image_pdf_bytes(),
        max_upload_bytes=1024 * 1024,
    )

    with pytest.raises(EmptyDocumentError, match="image-only|OCR"):
        extract_document(upload)


def test_mock_ocr_extracts_pages_with_stable_offsets() -> None:
    upload = validate_upload(
        filename="handwritten.pdf",
        content_type="application/pdf",
        data=_image_pdf_bytes(page_count=2),
        max_upload_bytes=1024 * 1024,
    )
    provider = MockOCRProvider(["First OCR page.", "Second OCR page."])

    processed = process_upload(
        upload,
        ocr_enabled=True,
        ocr_provider=provider,
    )

    assert processed.extractor_name == "PyMuPDF+TrOCR"
    assert [page.page_number for page in processed.page_map] == [1, 2]
    assert all(page.extraction_method == "ocr" for page in processed.page_map)
    assert all(page.ocr_confidence is None for page in processed.page_map)
    assert processed.extracted_text[processed.page_map[0].extracted_char_start:
                                      processed.page_map[0].extracted_char_end].startswith(
        "First OCR page."
    )
    assert processed.extracted_text[processed.page_map[1].extracted_char_start:
                                      processed.page_map[1].extracted_char_end].startswith(
        "Second OCR page."
    )


def test_unreadable_mock_ocr_page_returns_understandable_error() -> None:
    upload = validate_upload(
        filename="blank-scan.pdf",
        content_type="application/pdf",
        data=_image_pdf_bytes(),
        max_upload_bytes=1024 * 1024,
    )

    with pytest.raises(OCRUnreadableError, match="clearer scan|typed document"):
        extract_document(
            upload,
            ocr_enabled=True,
            ocr_provider=MockOCRProvider(),
        )


def test_missing_ocr_dependency_is_safe() -> None:
    class MissingDependencyProvider:
        def recognize_page(self, image_bytes: bytes) -> OCRPageResult:
            raise OCRDependencyError(
                "OCR dependencies are missing. Install requirements-ocr.txt."
            )

    upload = validate_upload(
        filename="missing-ocr.pdf",
        content_type="application/pdf",
        data=_image_pdf_bytes(),
        max_upload_bytes=1024 * 1024,
    )

    with pytest.raises(OCRDependencyError, match="requirements-ocr.txt"):
        extract_document(
            upload,
            ocr_enabled=True,
            ocr_provider=MissingDependencyProvider(),
        )


def test_docx_extraction_includes_paragraphs_and_tables() -> None:
    upload = validate_upload(
        filename="essay.docx",
        content_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        data=_docx_bytes(),
        max_upload_bytes=1024 * 1024,
    )
    extracted = extract_document(upload)

    assert "First DOCX paragraph." in extracted.text
    assert "First DOCX paragraph.\n\nTable evidence" in extracted.text
    assert "Table evidence" in extracted.text
    assert "Second cell" in extracted.text
    assert extracted.pages[0].page_number is None


@pytest.mark.parametrize("active_content", ["attachment", "javascript"])
def test_pdf_extraction_rejects_active_content(active_content: str) -> None:
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), "Safe visible text.")
    if active_content == "attachment":
        document.embfile_add("attachment.txt", b"untrusted content")
    else:
        document.xref_set_key(
            document.pdf_catalog(),
            "OpenAction",
            "<< /S /JavaScript /JS (app.alert) >>",
        )
    data = document.tobytes()
    document.close()
    upload = validate_upload(
        filename="active.pdf",
        content_type="application/pdf",
        data=data,
        max_upload_bytes=1024 * 1024,
    )

    with pytest.raises(InvalidDocumentError):
        extract_document(upload)


def test_pdf_attachment_is_rejected_before_ocr_provider_runs() -> None:
    document = pymupdf.open(stream=_image_pdf_bytes(), filetype="pdf")
    document.embfile_add("Content Credentials", b"credential metadata")
    data = document.tobytes()
    document.close()
    upload = validate_upload(
        filename="attached-scan.pdf",
        content_type="application/pdf",
        data=data,
        max_upload_bytes=1024 * 1024,
    )
    provider = MockOCRProvider(["OCR output"])

    with pytest.raises(InvalidDocumentError, match="embedded attachments"):
        extract_document(
            upload,
            ocr_enabled=True,
            ocr_provider=provider,
        )

    assert provider.calls == 0


def test_pdf_extraction_rejects_corrupt_file_with_pdf_signature() -> None:
    upload = validate_upload(
        filename="corrupt.pdf",
        content_type="application/pdf",
        data=b"%PDF-1.7\nnot a valid PDF body",
        max_upload_bytes=1024,
    )

    with pytest.raises(InvalidDocumentError):
        extract_document(upload)


@pytest.mark.parametrize(
    ("filename", "content_type", "data", "error"),
    [
        ("essay.exe", "application/octet-stream", b"not a document", UnsupportedDocumentError),
        ("essay.pdf", "text/plain", b"%PDF-1.7", UnsupportedDocumentError),
        ("essay.pdf", "application/pdf", b"not a pdf", InvalidDocumentError),
        ("essay.txt", "text/plain", b"", EmptyDocumentError),
        ("essay.txt", "text/plain", b"\x00binary", InvalidDocumentError),
        ("essay.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK\x03\x04invalid", InvalidDocumentError),
    ],
)
def test_upload_validation_rejects_invalid_files(
    filename: str,
    content_type: str,
    data: bytes,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        validate_upload(
            filename=filename,
            content_type=content_type,
            data=data,
            max_upload_bytes=1024,
        )


def test_upload_validation_rejects_oversized_and_macro_docx() -> None:
    with pytest.raises(UploadTooLargeError):
        validate_upload(
            filename="essay.txt",
            content_type="text/plain",
            data=b"0123456789",
            max_upload_bytes=9,
        )

    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr("word/document.xml", "<document/>")
        package.writestr("word/vbaProject.bin", b"macro")
    with pytest.raises(InvalidDocumentError):
        validate_upload(
            filename="essay.docx",
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            data=archive.getvalue(),
            max_upload_bytes=1024 * 1024,
        )


@pytest.mark.asyncio
async def test_upload_endpoint_rejects_file_over_configured_limit(
    client: AsyncClient,
    test_session_factory: sessionmaker,
    test_settings: Settings,
) -> None:
    test_settings.max_upload_mb = 1
    student = _create_user(
        test_session_factory,
        email="document-oversized@example.com",
        role=UserRole.STUDENT,
    )
    response = await client.post(
        "/api/v1/essays",
        files={
            "file": (
                "oversized.txt",
                b"x" * (test_settings.max_upload_bytes + 1),
                "text/plain",
            )
        },
        headers={"Authorization": f"Bearer {_token(student.id, test_settings)}"},
    )

    assert response.status_code == 413
    with test_session_factory() as session:
        assert session.scalar(
            select(Essay.id).where(Essay.student_id == student.id)
        ) is None


@pytest.mark.asyncio
async def test_upload_request_middleware_rejects_over_limit_body() -> None:
    async def app(*args: object, **kwargs: object) -> None:
        assert args and kwargs
        pytest.fail("Oversized upload should be rejected before reaching the app.")

    middleware = UploadRequestSizeLimitMiddleware(app, max_file_bytes=1)
    body = b"x" * (1 + 64 * 1024 + 1)
    messages = []
    received = False

    async def receive() -> dict[str, object]:
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    await middleware(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/essays",
            "headers": [],
        },
        receive,
        send,
    )

    assert messages[0]["status"] == 413


def test_upload_validation_rejects_docx_entity_declarations() -> None:
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("[Content_Types].xml", "<Types/>")
        package.writestr(
            "word/document.xml",
            '<!DOCTYPE document [<!ENTITY x SYSTEM "file:///sensitive">]>'
            "<document>&x;</document>",
        )

    with pytest.raises(InvalidDocumentError):
        validate_upload(
            filename="essay.docx",
            content_type=(
                "application/vnd.openxmlformats-officedocument."
                "wordprocessingml.document"
            ),
            data=archive.getvalue(),
            max_upload_bytes=1024 * 1024,
        )


def test_local_storage_uses_generated_names_and_rejects_traversal(tmp_path) -> None:
    storage = LocalEssayStorage(tmp_path)
    path = storage.save(
        essay_id=UUID("1b671a64-40d5-491e-99b0-da01ff1f3341"),
        extension=".txt",
        data=b"private essay",
    )

    assert path == "essays/1b671a6440d5491e99b0da01ff1f3341.txt"
    assert (tmp_path / Path(path)).read_bytes() == b"private essay"
    with pytest.raises(StorageError):
        storage.remove("../outside.txt")
    storage.remove(path)
    assert not (tmp_path / Path(path)).exists()


@pytest.mark.asyncio
async def test_upload_and_retrieval_enforce_course_membership_and_ownership(
    client: AsyncClient,
    test_session_factory: sessionmaker,
    test_settings: Settings,
) -> None:
    student = _create_user(
        test_session_factory,
        email="document-student@example.com",
        role=UserRole.STUDENT,
    )
    other_student = _create_user(
        test_session_factory,
        email="document-other-student@example.com",
        role=UserRole.STUDENT,
    )
    faculty = _create_user(
        test_session_factory,
        email="document-faculty@example.com",
        role=UserRole.FACULTY,
    )
    other_faculty = _create_user(
        test_session_factory,
        email="document-other-faculty@example.com",
        role=UserRole.FACULTY,
    )
    admin = _create_user(
        test_session_factory,
        email="document-admin@example.com",
        role=UserRole.ADMIN,
    )
    faculty_headers = {"Authorization": f"Bearer {_token(faculty.id, test_settings)}"}
    student_headers = {"Authorization": f"Bearer {_token(student.id, test_settings)}"}
    other_student_headers = {
        "Authorization": f"Bearer {_token(other_student.id, test_settings)}"
    }
    other_faculty_headers = {
        "Authorization": f"Bearer {_token(other_faculty.id, test_settings)}"
    }
    admin_headers = {"Authorization": f"Bearer {_token(admin.id, test_settings)}"}

    unauthenticated = await client.post(
        "/api/v1/essays",
        files={"file": ("essay.txt", b"Evidence belongs to a student.", "text/plain")},
    )
    assert unauthenticated.status_code == 401

    course_response = await client.post(
        "/api/v1/courses",
        json={"name": "Writing 101", "code": "write-101"},
        headers=faculty_headers,
    )
    assert course_response.status_code == 201
    course_id = course_response.json()["id"]
    enrollment = await client.post(
        f"/api/v1/courses/{course_id}/enrollments",
        json={"user_id": str(student.id), "role": "student"},
        headers=faculty_headers,
    )
    assert enrollment.status_code == 201

    upload = await client.post(
        "/api/v1/essays",
        data={"course_id": course_id},
        files={
            "file": (
                "student-essay.txt",
                b"Evidence belongs to a student. The exact text is preserved.",
                "text/plain",
            )
        },
        headers=student_headers,
    )
    assert upload.status_code == 201
    essay = upload.json()
    essay_id = essay["id"]
    assert essay["student_id"] == str(student.id)
    assert essay["course_id"] == course_id
    assert "stored_path" not in essay
    assert essay["page_map"][0]["page_number"] is None

    unapproved_course_upload = await client.post(
        "/api/v1/essays",
        data={"course_id": course_id},
        files={
            "file": (
                "other-student.txt",
                b"This student is not enrolled.",
                "text/plain",
            )
        },
        headers=other_student_headers,
    )
    assert unapproved_course_upload.status_code == 404

    faculty_upload = await client.post(
        "/api/v1/essays",
        files={
            "file": (
                "faculty.txt",
                b"Faculty cannot upload as a student.",
                "text/plain",
            )
        },
        headers=faculty_headers,
    )
    assert faculty_upload.status_code == 403

    pdf_upload = await client.post(
        "/api/v1/essays",
        files={
            "file": (
                "pages.pdf",
                _pdf_bytes(["First page.", "Second page."]),
                "application/pdf",
            )
        },
        headers=student_headers,
    )
    assert pdf_upload.status_code == 201
    assert [page["page_number"] for page in pdf_upload.json()["page_map"]] == [1, 2]

    docx_upload = await client.post(
        "/api/v1/essays",
        files={
            "file": (
                "paragraphs.docx",
                _docx_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=student_headers,
    )
    assert docx_upload.status_code == 201

    text_response = await client.get(
        f"/api/v1/essays/{essay_id}/text",
        headers=student_headers,
    )
    assert text_response.status_code == 200
    assert "Evidence belongs to a student." in text_response.json()["extracted_text"]

    own = await client.get(
        f"/api/v1/essays/{essay_id}",
        headers=student_headers,
    )
    other_owner = await client.get(
        f"/api/v1/essays/{essay_id}",
        headers=other_student_headers,
    )
    enrolled_faculty = await client.get(
        f"/api/v1/essays/{essay_id}",
        headers=faculty_headers,
    )
    nonmember_faculty = await client.get(
        f"/api/v1/essays/{essay_id}",
        headers=other_faculty_headers,
    )
    administrator = await client.get(
        f"/api/v1/essays/{essay_id}",
        headers=admin_headers,
    )
    assert own.status_code == 200
    assert other_owner.status_code == 404
    assert enrolled_faculty.status_code == 200
    assert nonmember_faculty.status_code == 404
    assert administrator.status_code == 200

    owner_list = await client.get("/api/v1/essays", headers=student_headers)
    other_owner_list = await client.get(
        "/api/v1/essays",
        headers=other_student_headers,
    )
    faculty_list = await client.get("/api/v1/essays", headers=faculty_headers)
    nonmember_list = await client.get(
        "/api/v1/essays",
        headers=other_faculty_headers,
    )
    admin_list = await client.get("/api/v1/essays", headers=admin_headers)
    assert {item["id"] for item in owner_list.json()} == {
        essay_id,
        pdf_upload.json()["id"],
        docx_upload.json()["id"],
    }
    assert other_owner_list.json() == []
    assert [item["id"] for item in faculty_list.json()] == [essay_id]
    assert nonmember_list.json() == []
    assert {item["id"] for item in admin_list.json()} == {
        essay_id,
        pdf_upload.json()["id"],
        docx_upload.json()["id"],
    }

    with test_session_factory() as session:
        stored_essay = session.get(Essay, UUID(essay_id))
        assert stored_essay is not None
        assert (test_settings.resolved_file_storage_dir / stored_essay.stored_path).is_file()
        assert len(list(session.scalars(select(EssayChunk).where(EssayChunk.essay_id == stored_essay.id)))) > 0
        student_membership = session.scalar(
            select(Enrollment).where(Enrollment.user_id == student.id)
        )
        assert student_membership is not None
        assert student_membership.role is CourseMemberRole.STUDENT


@pytest.mark.asyncio
async def test_upload_rejects_invalid_mime_and_storage_failures(
    client: AsyncClient,
    test_session_factory: sessionmaker,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    student = _create_user(
        test_session_factory,
        email="document-failure@example.com",
        role=UserRole.STUDENT,
    )
    headers = {"Authorization": f"Bearer {_token(student.id, test_settings)}"}
    mismatch = await client.post(
        "/api/v1/essays",
        files={"file": ("essay.pdf", b"%PDF-1.7", "text/plain")},
        headers=headers,
    )
    assert mismatch.status_code == 415

    def fail_storage(*args: object, **kwargs: object) -> str:
        assert args and kwargs
        raise StorageError("test storage failure")

    monkeypatch.setattr(LocalEssayStorage, "save", fail_storage)
    failed = await client.post(
        "/api/v1/essays",
        files={
            "file": (
                "essay.txt",
                b"This is valid essay text.",
                "text/plain",
            )
        },
        headers=headers,
    )
    assert failed.status_code == 503
    with test_session_factory() as session:
        assert session.scalar(
            select(Essay.id).where(Essay.student_id == student.id)
        ) is None
