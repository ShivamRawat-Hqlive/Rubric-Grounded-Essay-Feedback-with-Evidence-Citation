"""Essay upload and retrieval API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.models.essay import EssayParseStatus


class PageMetadataResponse(BaseModel):
    page_number: int | None
    extracted_char_start: int
    extracted_char_end: int
    normalized_char_start: int
    normalized_char_end: int
    extraction_method: str = "native"
    ocr_confidence: float | None = None


class EssayResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    course_id: UUID | None
    original_filename: str
    content_type: str
    size_bytes: int
    parse_status: EssayParseStatus
    normalizer_version: str
    page_map: list[PageMetadataResponse]
    extractor_name: str
    extractor_version: str
    sha256: str
    created_at: datetime


class EssayTextResponse(BaseModel):
    extracted_text: str
    normalized_text: str
    normalizer_version: str
    offset_alignment: list[list[int]]
    page_map: list[PageMetadataResponse]
