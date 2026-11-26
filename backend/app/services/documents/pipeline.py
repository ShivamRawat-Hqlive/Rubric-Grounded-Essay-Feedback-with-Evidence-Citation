"""Synchronous processing from validated upload to aligned sentence chunks."""

from dataclasses import dataclass

from app.services.documents.alignment import (
    AlignmentTooComplexError,
    map_normalized_span,
    map_source_span_to_normalized,
)
from app.services.documents.chunker import SentenceChunk, split_sentences
from app.services.documents.extractor import (
    EmptyDocumentError,
    ExtractedDocument,
    ExtractedPage,
    InvalidDocumentError,
    ValidatedUpload,
    extract_document,
)
from app.services.documents.preprocessor import NORMALIZER_VERSION, normalize_text
from app.services.documents.ocr import OCRProvider


@dataclass(frozen=True)
class PageMetadata:
    page_number: int | None
    extracted_char_start: int
    extracted_char_end: int
    normalized_char_start: int
    normalized_char_end: int
    extraction_method: str = "native"
    ocr_confidence: float | None = None


@dataclass(frozen=True)
class AlignedChunk:
    sentence_index: int
    char_start: int
    char_end: int
    extracted_char_start: int
    extracted_char_end: int
    page_start: int | None
    page_end: int | None
    text: str


@dataclass(frozen=True)
class ProcessedDocument:
    extracted_text: str
    normalized_text: str
    normalizer_version: str
    offset_alignment: list[list[int]]
    page_map: list[PageMetadata]
    extractor_name: str
    extractor_version: str
    chunks: list[AlignedChunk]


def _normalize_page(
    page: ExtractedPage,
    alignment: list[list[int]],
) -> PageMetadata:
    normalized_start, normalized_end = map_source_span_to_normalized(
        alignment,
        page.extracted_char_start,
        page.extracted_char_end,
    )
    return PageMetadata(
        page_number=page.page_number,
        extracted_char_start=page.extracted_char_start,
        extracted_char_end=page.extracted_char_end,
        normalized_char_start=normalized_start,
        normalized_char_end=normalized_end,
        extraction_method=page.extraction_method,
        ocr_confidence=page.ocr_confidence,
    )


def _align_chunk(
    chunk: SentenceChunk,
    alignment: list[list[int]],
    pages: list[PageMetadata],
) -> AlignedChunk:
    extracted_start, extracted_end = map_normalized_span(
        alignment, chunk.char_start, chunk.char_end
    )
    page_numbers = [
        page.page_number
        for page in pages
        if page.page_number is not None
        and page.normalized_char_start < chunk.char_end
        and chunk.char_start < page.normalized_char_end
    ]
    return AlignedChunk(
        sentence_index=chunk.sentence_index,
        char_start=chunk.char_start,
        char_end=chunk.char_end,
        extracted_char_start=extracted_start,
        extracted_char_end=extracted_end,
        page_start=min(page_numbers) if page_numbers else None,
        page_end=max(page_numbers) if page_numbers else None,
        text=chunk.text,
    )


def process_upload(
    upload: ValidatedUpload,
    *,
    max_extracted_characters: int = 500_000,
    ocr_enabled: bool = False,
    ocr_provider: OCRProvider | None = None,
) -> ProcessedDocument:
    extracted: ExtractedDocument = extract_document(
        upload,
        max_extracted_characters=max_extracted_characters,
        ocr_enabled=ocr_enabled,
        ocr_provider=ocr_provider,
    )
    try:
        normalized_text, alignment = normalize_text(
            extracted.text,
            max_characters=max_extracted_characters,
        )
    except (AlignmentTooComplexError, ValueError) as exc:
        raise InvalidDocumentError(
            "The document is too complex to process safely."
        ) from exc
    if not normalized_text.strip():
        raise EmptyDocumentError("The document contains no usable text after normalization.")

    pages = [_normalize_page(page, alignment) for page in extracted.pages]
    sentence_chunks = split_sentences(normalized_text)
    chunks = [_align_chunk(chunk, alignment, pages) for chunk in sentence_chunks]
    return ProcessedDocument(
        extracted_text=extracted.text,
        normalized_text=normalized_text,
        normalizer_version=NORMALIZER_VERSION,
        offset_alignment=alignment,
        page_map=pages,
        extractor_name=extracted.extractor_name,
        extractor_version=extracted.extractor_version,
        chunks=chunks,
    )
