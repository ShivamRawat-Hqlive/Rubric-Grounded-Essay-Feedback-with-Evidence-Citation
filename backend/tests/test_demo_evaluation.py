import pytest
import pymupdf

from app.api.v1.demo import _evaluations, _evaluations_lock


@pytest.fixture(autouse=True)
def clear_demo_evaluations():
    with _evaluations_lock:
        _evaluations.clear()
    yield
    with _evaluations_lock:
        _evaluations.clear()


@pytest.mark.asyncio
async def test_local_demo_upload_cites_exact_text_and_faculty_can_approve(client):
    essay_text = (
        "Students should learn to assess sources because evidence supports a claim. "
        "However, they should also compare different perspectives. "
        "For example, careful reading helps writers explain their reasoning."
    )
    response = await client.post(
        "/api/v1/demo/evaluations",
        files={"file": ("sample.txt", essay_text.encode("utf-8"), "text/plain")},
    )

    assert response.status_code == 201
    evaluation = response.json()
    assert evaluation["evaluation_mode"] == "local_demo"
    assert evaluation["demo_label"] == "DEMO-GENERATED — NOT AI"
    assert evaluation["status"] == "needs_review"
    assert sum(criterion["weight_percent"] for criterion in evaluation["criteria"]) == 100
    assert len(evaluation["criteria"]) == 5
    for criterion in evaluation["criteria"]:
        for citation in criterion["evidence_quotes"]:
            start = citation["extracted_char_start"]
            end = citation["extracted_char_end"]
            assert essay_text[start:end] == citation["quoted_text"]
            assert citation["existence_verified"] is True
            assert citation["page_number"] is None

    faculty_queue = await client.get("/api/v1/demo/evaluations")
    assert faculty_queue.status_code == 200
    assert len(faculty_queue.json()) == 1

    review_response = await client.post(
        f"/api/v1/demo/evaluations/{evaluation['id']}/review",
        json={"action": "approved", "note": "Reviewed in the local demo."},
    )
    assert review_response.status_code == 200
    assert review_response.json()["status"] == "approved"
    assert review_response.json()["faculty_note"] == "Reviewed in the local demo."

    student_result = await client.get(
        f"/api/v1/demo/evaluations/{evaluation['id']}"
    )
    assert student_result.status_code == 200
    assert student_result.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_demo_rejects_docx_and_empty_text_with_actionable_errors(client):
    unsupported = await client.post(
        "/api/v1/demo/evaluations",
        files={
            "file": (
                "essay.docx",
                b"not-a-real-docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert unsupported.status_code == 415
    assert "PDF and plain-text TXT" in unsupported.json()["detail"]

    empty = await client.post(
        "/api/v1/demo/evaluations",
        files={"file": ("empty.txt", b"  \n", "text/plain")},
    )
    assert empty.status_code == 422
    assert "no usable text" in empty.json()["detail"]


@pytest.mark.asyncio
async def test_demo_extracts_text_pdf_and_preserves_page_reference(client):
    source_text = (
        "Clear arguments explain evidence. "
        "However, authors should consider another perspective."
    )
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), source_text)
    pdf_bytes = document.tobytes()
    document.close()

    response = await client.post(
        "/api/v1/demo/evaluations",
        files={"file": ("sample.pdf", pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 201
    result = response.json()
    assert result["extractor_name"] == "PyMuPDF"
    assert result["page_map"][0]["page_number"] == 1
    assert result["page_map"][0]["extraction_method"] == "native"
    assert result["page_map"][0]["extracted_char_start"] == 0
    assert result["page_map"][0]["extracted_char_end"] == len(result["extracted_text"])
    quotes = [
        quote
        for criterion in result["criteria"]
        for quote in criterion["evidence_quotes"]
    ]
    assert quotes
    assert all(quote["page_number"] == 1 for quote in quotes)
    assert all(
        result["extracted_text"][quote["extracted_char_start"]:quote["extracted_char_end"]]
        == quote["quoted_text"]
        for quote in quotes
    )
