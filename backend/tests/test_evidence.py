"""Local retrieval and exact evidence-location validation tests."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.schemas.evaluation import ClaimEvaluationOutput
from app.services.documents.alignment import map_normalized_span
from app.services.documents.preprocessor import normalize_text
from app.services.evidence import (
    EvidenceValidationError,
    retrieve_candidate_passages,
    validate_claims,
)


def _essay(text: str, *, page_map: list[dict[str, int | None]] | None = None):
    normalized_text, alignment = normalize_text(text)
    return SimpleNamespace(
        id=uuid4(),
        extracted_text=text,
        normalized_text=normalized_text,
        normalizer_version="v1",
        offset_alignment=alignment,
        page_map=page_map or [],
        extractor_name="UTF-8",
        extractor_version="1",
    )


def _chunk(essay, text: str, chunk_index: int):
    normalized_start = essay.normalized_text.index(text)
    normalized_end = normalized_start + len(text)
    extracted_start, extracted_end = map_normalized_span(
        essay.offset_alignment,
        normalized_start,
        normalized_end,
    )
    return SimpleNamespace(
        id=uuid4(),
        essay_id=essay.id,
        chunk_index=chunk_index,
        text=essay.normalized_text[normalized_start:normalized_end],
        char_start=normalized_start,
        char_end=normalized_end,
        extracted_char_start=extracted_start,
        extracted_char_end=extracted_end,
        page_start=None,
        page_end=None,
    )


def _claim(chunk_id, quoted_text: str) -> ClaimEvaluationOutput:
    return ClaimEvaluationOutput.model_validate(
        {
            "text": "The excerpt relates to the criterion.",
            "evidence_quotes": [
                {
                    "chunk_id": str(chunk_id),
                    "quoted_text": quoted_text,
                    "reason": "The excerpt is a candidate for review.",
                }
            ],
        }
    )


def _candidate_passages(essay, chunks):
    return retrieve_candidate_passages(
        essay,
        chunks,
        SimpleNamespace(
            name="Evidence",
            description="Assess evidence.",
            levels_json=[],
        ),
    )


def test_exact_quote_has_original_and_normalized_offsets_and_locations() -> None:
    text = "Introduction sentence.\n\nEvidence sentence.\n\nConclusion sentence."
    quote = "Evidence sentence."
    page_boundary = len("Introduction sentence.\n\n")
    essay = _essay(
        text,
        page_map=[
            {
                "page_number": 1,
                "extracted_char_start": 0,
                "extracted_char_end": page_boundary,
                "normalized_char_start": 0,
                "normalized_char_end": page_boundary,
            },
            {
                "page_number": 2,
                "extracted_char_start": page_boundary,
                "extracted_char_end": len(text),
                "normalized_char_start": page_boundary,
                "normalized_char_end": len(text),
            },
        ],
    )
    chunk = _chunk(essay, quote, 0)
    claims, unsupported = validate_claims(
        essay,
        [_claim(chunk.id, quote)],
        retrieve_candidate_passages(
            essay,
            [chunk],
            SimpleNamespace(
                name="Evidence",
                description="Assess evidence.",
                levels_json=[],
            ),
        ),
    )
    evidence = claims[0].evidence_quotes[0]
    start = text.index(quote)

    assert not unsupported
    assert evidence.extracted_char_start == start
    assert evidence.extracted_char_end == start + len(quote)
    assert essay.extracted_text[
        evidence.extracted_char_start : evidence.extracted_char_end
    ] == quote
    assert essay.normalized_text[
        evidence.normalized_char_start : evidence.normalized_char_end
    ] == quote
    assert (evidence.paragraph_start, evidence.paragraph_end) == (2, 2)
    assert (evidence.page_start, evidence.page_end) == (2, 2)
    assert evidence.model_relevance_rationale == (
        "The excerpt is a candidate for review."
    )


def test_original_quote_offsets_map_through_normalization() -> None:
    text = "A\t\tsource with “quoted” evidence."
    quote = "“quoted”"
    essay = _essay(text)
    chunk = _chunk(essay, essay.normalized_text, 0)

    claims, _ = validate_claims(
        essay,
        [_claim(chunk.id, quote)],
        _candidate_passages(essay, [chunk]),
    )
    evidence = claims[0].evidence_quotes[0]

    assert essay.extracted_text[
        evidence.extracted_char_start : evidence.extracted_char_end
    ] == quote
    assert (
        essay.normalized_text[
            evidence.normalized_char_start : evidence.normalized_char_end
        ]
        == '"quoted"'
    )
    assert evidence.extracted_char_start == text.index(quote)

def test_ocr_extracted_text_supports_exact_evidence_locations() -> None:
    text = "First OCR page.\n\f\nSecond OCR page."
    quote = "Second OCR page."
    essay = _essay(
        text,
        page_map=[
            {
                "page_number": 1,
                "extracted_char_start": 0,
                "extracted_char_end": len("First OCR page.\n"),
                "normalized_char_start": 0,
                "normalized_char_end": len("First OCR page.\n"),
                "extraction_method": "ocr",
                "ocr_confidence": None,
            },
            {
                "page_number": 2,
                "extracted_char_start": len("First OCR page.\n") + 3,
                "extracted_char_end": len(text),
                "normalized_char_start": len("First OCR page.\n") + 3,
                "normalized_char_end": len(text),
                "extraction_method": "ocr",
                "ocr_confidence": None,
            },
        ],
    )
    essay.extractor_name = "PyMuPDF+TrOCR"
    essay.extractor_version = "1.0-blocks-v1"
    chunk = _chunk(essay, quote, 0)

    claims, unsupported = validate_claims(
        essay,
        [_claim(chunk.id, quote)],
        _candidate_passages(essay, [chunk]),
    )

    evidence = claims[0].evidence_quotes[0]
    assert not unsupported
    assert evidence.quoted_text == quote
    assert evidence.extracted_char_start >= 0
    assert essay.extracted_text[
        evidence.extracted_char_start:evidence.extracted_char_end
    ] == quote
    assert (evidence.page_start, evidence.page_end) == (2, 2)


def test_pdf_block_paragraph_location_is_reported() -> None:
    text = "First block.\n\nSecond block."
    quote = "Second block."
    essay = _essay(
        text,
        page_map=[
            {
                "page_number": 1,
                "extracted_char_start": 0,
                "extracted_char_end": len(text),
                "normalized_char_start": 0,
                "normalized_char_end": len(text),
            }
        ],
    )
    essay.extractor_name = "PyMuPDF"
    essay.extractor_version = "1.0-blocks-v1"
    chunk = _chunk(essay, essay.normalized_text, 0)

    claims, _ = validate_claims(
        essay,
        [_claim(chunk.id, quote)],
        _candidate_passages(essay, [chunk]),
    )

    evidence = claims[0].evidence_quotes[0]
    assert (evidence.paragraph_start, evidence.paragraph_end) == (2, 2)
    assert (evidence.page_start, evidence.page_end) == (1, 1)


def test_unmatched_quote_is_rejected() -> None:
    essay = _essay("The submitted essay contains an original sentence.")
    chunk = _chunk(essay, essay.normalized_text, 0)

    with pytest.raises(EvidenceValidationError, match="not found"):
        validate_claims(
            essay,
            [_claim(chunk.id, "invented quotation")],
            _candidate_passages(essay, [chunk]),
        )


def test_repeated_quote_within_a_chunk_is_rejected_as_ambiguous() -> None:
    text = "Repeat this evidence. Then Repeat this evidence."
    essay = _essay(text)
    chunk = _chunk(essay, essay.normalized_text, 0)

    with pytest.raises(EvidenceValidationError, match="ambiguous"):
        validate_claims(
            essay,
            [_claim(chunk.id, "Repeat this evidence.")],
            _candidate_passages(essay, [chunk]),
        )


def test_quote_must_reference_a_retrieved_chunk() -> None:
    essay = _essay("A sentence with source evidence.")
    chunk = _chunk(essay, essay.normalized_text, 0)

    with pytest.raises(EvidenceValidationError, match="not retrieved"):
        validate_claims(
            essay,
            [_claim(uuid4(), "source evidence")],
            _candidate_passages(essay, [chunk]),
        )


def test_empty_evidence_is_flagged_without_inventing_a_citation() -> None:
    essay = _essay("A sentence without any citations.")
    claim = ClaimEvaluationOutput.model_validate(
        {"text": "No excerpt was found.", "evidence_quotes": []}
    )

    claims, unsupported = validate_claims(essay, [claim], [])

    assert unsupported
    assert claims[0].evidence_quotes == []


def test_local_ranker_orders_relevant_passages_deterministically() -> None:
    essay = _essay("Pasta cooks quickly.\n\nClimate policy reduces emissions.")
    chunks = [
        _chunk(essay, "Pasta cooks quickly.", 0),
        _chunk(essay, "Climate policy reduces emissions.", 1),
    ]
    criterion = SimpleNamespace(
        name="Climate policy",
        description="Evaluate emissions evidence.",
        levels_json=[],
    )

    ranked = retrieve_candidate_passages(essay, chunks, criterion)

    assert [passage.chunk_index for passage in ranked] == [1, 0]
