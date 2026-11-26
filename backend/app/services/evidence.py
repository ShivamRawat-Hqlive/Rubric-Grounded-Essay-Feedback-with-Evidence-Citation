"""Local passage retrieval and exact evidence-location validation."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from app.db.models.essay import Essay, EssayChunk
from app.db.models.rubric import RubricCriterion
from app.schemas.evaluation import ClaimEvaluationOutput
from app.services.documents.alignment import (
    map_normalized_span,
    map_source_span_to_normalized,
)

MAX_CANDIDATE_PASSAGES = 5
_WORD_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
_PARAGRAPH_BREAK = re.compile(r"(?:\r\n|\r|\n)[ \t]*(?:(?:\r\n|\r|\n)[ \t]*)+")
_PARAGRAPH_OR_PAGE_BREAK = re.compile(
    rf"\n\f\n|{_PARAGRAPH_BREAK.pattern}"
)


class EvidenceIntegrityError(RuntimeError):
    """Raised when persisted essay chunks or offsets are inconsistent."""


class EvidenceValidationError(RuntimeError):
    """Raised when provider-generated evidence cannot be verified exactly."""


@dataclass(frozen=True)
class CandidatePassage:
    chunk_id: UUID
    chunk_index: int
    normalized_text: str
    source_text: str
    normalized_char_start: int
    normalized_char_end: int
    extracted_char_start: int
    extracted_char_end: int
    page_start: int | None
    page_end: int | None

    def as_prompt_data(self) -> dict[str, str]:
        return {"chunk_id": str(self.chunk_id), "text": self.source_text}


@dataclass(frozen=True)
class VerifiedEvidenceQuote:
    source_chunk_id: UUID
    quoted_text: str
    model_relevance_rationale: str
    extracted_char_start: int
    extracted_char_end: int
    normalized_char_start: int
    normalized_char_end: int
    paragraph_start: int | None
    paragraph_end: int | None
    page_start: int | None
    page_end: int | None

    def as_json(self) -> dict[str, object]:
        return {
            "source_chunk_id": str(self.source_chunk_id),
            "quoted_text": self.quoted_text,
            "model_relevance_rationale": self.model_relevance_rationale,
            "existence_status": "verified",
            "relevance_status": "unverified",
            "extracted_char_start": self.extracted_char_start,
            "extracted_char_end": self.extracted_char_end,
            "normalized_char_start": self.normalized_char_start,
            "normalized_char_end": self.normalized_char_end,
            "paragraph_start": self.paragraph_start,
            "paragraph_end": self.paragraph_end,
            "page_start": self.page_start,
            "page_end": self.page_end,
        }


@dataclass(frozen=True)
class VerifiedClaim:
    text: str
    evidence_quotes: list[VerifiedEvidenceQuote]

    def as_json(self) -> dict[str, object]:
        return {
            "text": self.text,
            "evidence_quotes": [
                quote.as_json() for quote in self.evidence_quotes
            ],
        }


def _tokens(text: str) -> set[str]:
    return {match.group(0).casefold() for match in _WORD_PATTERN.finditer(text)}


def _criterion_query(criterion: RubricCriterion) -> str:
    level_descriptions = " ".join(
        str(level.get("description", ""))
        for level in criterion.levels_json
        if isinstance(level, dict)
    )
    return " ".join((criterion.name, criterion.description, level_descriptions))


def _page_ranges(essay: Essay) -> list[tuple[int, int, int]]:
    ranges: list[tuple[int, int, int]] = []
    for page in essay.page_map:
        page_number = page.get("page_number")
        start = page.get("extracted_char_start")
        end = page.get("extracted_char_end")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 0
            or end < start
            or end > len(essay.extracted_text)
            or (
                page_number is not None
                and (
                    not isinstance(page_number, int)
                    or isinstance(page_number, bool)
                    or page_number <= 0
                )
            )
        ):
            raise EvidenceIntegrityError("The essay has invalid page metadata.")
        if page_number is not None:
            ranges.append((page_number, start, end))
    return ranges


def retrieve_candidate_passages(
    essay: Essay,
    chunks: Sequence[EssayChunk],
    criterion: RubricCriterion,
    *,
    limit: int = MAX_CANDIDATE_PASSAGES,
) -> list[CandidatePassage]:
    if limit <= 0:
        raise ValueError("The candidate passage limit must be positive.")
    query_tokens = _tokens(_criterion_query(criterion))
    page_ranges = _page_ranges(essay)
    ranked: list[tuple[int, int, CandidatePassage]] = []

    for chunk in chunks:
        if chunk.essay_id != essay.id:
            raise EvidenceIntegrityError("An essay chunk belongs to a different essay.")
        if (
            chunk.char_start < 0
            or chunk.char_end <= chunk.char_start
            or chunk.char_end > len(essay.normalized_text)
            or chunk.extracted_char_start < 0
            or chunk.extracted_char_end <= chunk.extracted_char_start
            or chunk.extracted_char_end > len(essay.extracted_text)
        ):
            raise EvidenceIntegrityError("An essay chunk has invalid character offsets.")

        normalized_text = essay.normalized_text[chunk.char_start : chunk.char_end]
        source_text = essay.extracted_text[
            chunk.extracted_char_start : chunk.extracted_char_end
        ]
        if not source_text or normalized_text != chunk.text:
            raise EvidenceIntegrityError("An essay chunk does not match stored essay text.")
        try:
            mapped_source_span = map_normalized_span(
                essay.offset_alignment,
                chunk.char_start,
                chunk.char_end,
            )
        except ValueError as exc:
            raise EvidenceIntegrityError(
                "An essay chunk is not covered by its stored offset alignment."
            ) from exc
        if mapped_source_span != (
            chunk.extracted_char_start,
            chunk.extracted_char_end,
        ):
            raise EvidenceIntegrityError(
                "An essay chunk disagrees with its stored offset alignment."
            )

        page_numbers = [
            number
            for number, page_start, page_end in page_ranges
            if chunk.extracted_char_start < page_end
            and page_start < chunk.extracted_char_end
        ]
        passage = CandidatePassage(
            chunk_id=chunk.id,
            chunk_index=chunk.chunk_index,
            normalized_text=normalized_text,
            source_text=source_text,
            normalized_char_start=chunk.char_start,
            normalized_char_end=chunk.char_end,
            extracted_char_start=chunk.extracted_char_start,
            extracted_char_end=chunk.extracted_char_end,
            page_start=min(page_numbers) if page_numbers else None,
            page_end=max(page_numbers) if page_numbers else None,
        )
        overlap = len(query_tokens.intersection(_tokens(normalized_text)))
        ranked.append((overlap, chunk.chunk_index, passage))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [passage for _, _, passage in ranked[:limit]]


def _paragraph_ranges(
    essay: Essay,
) -> list[tuple[int, int, int]]:
    text = essay.extracted_text
    if not text.strip():
        return []

    if essay.extractor_name == "python-docx" and not _PARAGRAPH_BREAK.search(text):
        separator = re.compile(r"\r\n|\r|\n")
    elif (
        essay.extractor_name.startswith("PyMuPDF")
        and not essay.extractor_version.endswith("-blocks-v1")
        and not _PARAGRAPH_BREAK.search(text)
    ):
        return []
    elif essay.extractor_name.startswith("PyMuPDF"):
        separator = _PARAGRAPH_OR_PAGE_BREAK
    else:
        separator = _PARAGRAPH_OR_PAGE_BREAK

    ranges: list[tuple[int, int, int]] = []
    cursor = 0
    for match in separator.finditer(text):
        start, end = cursor, match.start()
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start < end:
            ranges.append((len(ranges) + 1, start, end))
        cursor = match.end()

    start, end = cursor, len(text)
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start < end:
        ranges.append((len(ranges) + 1, start, end))
    return ranges


def _paragraph_location(
    paragraphs: Sequence[tuple[int, int, int]],
    start: int,
    end: int,
) -> tuple[int | None, int | None]:
    start_paragraph = next(
        (number for number, paragraph_start, paragraph_end in paragraphs
         if paragraph_start <= start < paragraph_end),
        None,
    )
    end_paragraph = next(
        (number for number, paragraph_start, paragraph_end in paragraphs
         if paragraph_start <= end - 1 < paragraph_end),
        None,
    )
    return start_paragraph, end_paragraph


def _page_location(
    pages: Sequence[tuple[int, int, int]],
    start: int,
    end: int,
) -> tuple[int | None, int | None]:
    page_numbers = [
        number
        for number, page_start, page_end in pages
        if start < page_end and page_start < end
    ]
    return (
        (min(page_numbers), max(page_numbers))
        if page_numbers
        else (None, None)
    )


def _unique_occurrence(text: str, quote: str) -> int:
    matches: list[int] = []
    search_from = 0
    while True:
        index = text.find(quote, search_from)
        if index < 0:
            break
        matches.append(index)
        if len(matches) > 1:
            break
        search_from = index + 1
    if not matches:
        raise EvidenceValidationError("A quoted excerpt was not found in its source passage.")
    if len(matches) > 1:
        raise EvidenceValidationError("A quoted excerpt has an ambiguous source location.")
    return matches[0]


def validate_claims(
    essay: Essay,
    claims: Sequence[ClaimEvaluationOutput],
    candidates: Sequence[CandidatePassage],
) -> tuple[list[VerifiedClaim], bool]:
    passages_by_id = {passage.chunk_id: passage for passage in candidates}
    paragraphs = _paragraph_ranges(essay)
    pages = _page_ranges(essay)
    verified_claims: list[VerifiedClaim] = []
    has_unsupported_claims = False

    for claim in claims:
        verified_quotes: list[VerifiedEvidenceQuote] = []
        if not claim.evidence_quotes:
            has_unsupported_claims = True
        for proposed_quote in claim.evidence_quotes:
            passage = passages_by_id.get(proposed_quote.chunk_id)
            if passage is None:
                raise EvidenceValidationError(
                    "A quoted excerpt referenced a passage that was not retrieved."
                )
            local_start = _unique_occurrence(
                passage.source_text,
                proposed_quote.quoted_text,
            )
            extracted_start = passage.extracted_char_start + local_start
            extracted_end = extracted_start + len(proposed_quote.quoted_text)
            if (
                essay.extracted_text[extracted_start:extracted_end]
                != proposed_quote.quoted_text
            ):
                raise EvidenceValidationError(
                    "A quoted excerpt did not match the stored essay text."
                )
            try:
                normalized_start, normalized_end = map_source_span_to_normalized(
                    essay.offset_alignment,
                    extracted_start,
                    extracted_end,
                )
            except ValueError as exc:
                raise EvidenceIntegrityError(
                    "A verified excerpt could not be mapped to normalized essay text."
                ) from exc
            if (
                normalized_start < 0
                or normalized_end <= normalized_start
                or normalized_end > len(essay.normalized_text)
            ):
                raise EvidenceIntegrityError(
                    "A verified excerpt mapped outside normalized essay text."
                )
            paragraph_start, paragraph_end = _paragraph_location(
                paragraphs,
                extracted_start,
                extracted_end,
            )
            page_start, page_end = _page_location(
                pages,
                extracted_start,
                extracted_end,
            )
            verified_quotes.append(
                VerifiedEvidenceQuote(
                    source_chunk_id=passage.chunk_id,
                    quoted_text=proposed_quote.quoted_text,
                    model_relevance_rationale=proposed_quote.reason,
                    extracted_char_start=extracted_start,
                    extracted_char_end=extracted_end,
                    normalized_char_start=normalized_start,
                    normalized_char_end=normalized_end,
                    paragraph_start=paragraph_start,
                    paragraph_end=paragraph_end,
                    page_start=page_start,
                    page_end=page_end,
                )
            )
        verified_claims.append(
            VerifiedClaim(text=claim.text, evidence_quotes=verified_quotes)
        )

    return verified_claims, has_unsupported_claims
