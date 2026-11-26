"""Validated PDF, DOCX, and UTF-8 text extraction."""

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
import re
import stat
import unicodedata
import zipfile

import docx
import pymupdf
from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml.etree import XMLSyntaxError
from app.services.documents.ocr import (
    OCRDependencyError,
    OCRPageRenderError,
    OCRProvider,
    OCRUnreadableError,
)


class UnsupportedDocumentError(ValueError):
    """Raised when an upload uses an unsupported extension or MIME type."""


class InvalidDocumentError(ValueError):
    """Raised when an upload is corrupt, unsafe, or cannot be extracted."""


class EmptyDocumentError(ValueError):
    """Raised when a valid document contains no usable text."""


class UploadTooLargeError(ValueError):
    """Raised when an upload exceeds the configured byte limit."""


@dataclass(frozen=True)
class ValidatedUpload:
    data: bytes
    filename: str
    extension: str
    content_type: str
    decoded_text: str | None = None


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int | None
    extracted_char_start: int
    extracted_char_end: int
    extraction_method: str = "native"
    ocr_confidence: float | None = None


@dataclass(frozen=True)
class ExtractedDocument:
    text: str
    pages: list[ExtractedPage]
    extractor_name: str
    extractor_version: str


_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
}
_MAX_ARCHIVE_MEMBERS = 4096
_MAX_XML_PART_BYTES = 10 * 1024 * 1024
_MAX_PDF_PAGES = 500


def _safe_filename(filename: str) -> tuple[str, str]:
    if len(filename) > 1024:
        raise UnsupportedDocumentError("The filename exceeds the allowed length.")
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    basename = unicodedata.normalize("NFC", basename)
    if not basename or any(unicodedata.category(char).startswith("C") for char in basename):
        raise UnsupportedDocumentError("A valid filename is required.")

    extension = "." + basename.rsplit(".", 1)[-1].lower() if "." in basename else ""
    if extension not in _CONTENT_TYPES:
        raise UnsupportedDocumentError("Only PDF, DOCX, and TXT files are supported.")

    stem = basename[: -len(extension)]
    safe_name = f"{stem[: 255 - len(extension)]}{extension}"
    if not stem or safe_name in (".", ".."):
        raise UnsupportedDocumentError("A valid filename is required.")
    return safe_name, extension


def _validate_docx_archive(data: bytes, max_upload_bytes: int) -> None:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > _MAX_ARCHIVE_MEMBERS:
                raise InvalidDocumentError("The DOCX package contains too many entries.")

            names: set[str] = set()
            total_uncompressed_bytes = 0
            max_uncompressed_bytes = max(50 * 1024 * 1024, max_upload_bytes * 5)
            for member in members:
                member_path = PurePosixPath(member.filename)
                if (
                    member_path.is_absolute()
                    or ".." in member_path.parts
                    or "\\" in member.filename
                    or member.filename in names
                    or stat.S_ISLNK(member.external_attr >> 16)
                ):
                    raise InvalidDocumentError("The DOCX package contains unsafe entries.")
                names.add(member.filename)
                total_uncompressed_bytes += member.file_size
                if total_uncompressed_bytes > max_uncompressed_bytes:
                    raise InvalidDocumentError("The DOCX package expands beyond the allowed size.")
                if (
                    member.file_size > 0
                    and member.file_size / max(member.compress_size, 1) > 1000
                ):
                    raise InvalidDocumentError("The DOCX package has suspicious compression.")

            if (
                "[Content_Types].xml" not in names
                or "word/document.xml" not in names
                or any(
                    name.lower().endswith("vbaproject.bin")
                    or "/embeddings/" in name.lower()
                    or "/activex/" in name.lower()
                    for name in names
                )
            ):
                raise InvalidDocumentError("The DOCX package is unsupported or contains active content.")

            for member in members:
                if member.filename.lower().endswith((".xml", ".rels")):
                    if member.file_size > _MAX_XML_PART_BYTES:
                        raise InvalidDocumentError(
                            "A DOCX XML part exceeds the processing limit."
                        )
                    with archive.open(member) as xml_part:
                        xml_content = xml_part.read(_MAX_XML_PART_BYTES + 1)
                    if (
                        len(xml_content) > _MAX_XML_PART_BYTES
                        or re.search(rb"<!DOCTYPE|<!ENTITY", xml_content, re.IGNORECASE)
                        or (
                            member.filename == "[Content_Types].xml"
                            and re.search(rb"macroEnabled", xml_content, re.IGNORECASE)
                        )
                    ):
                        raise InvalidDocumentError(
                            "The DOCX package contains unsupported active XML."
                        )

            if archive.testzip() is not None:
                raise InvalidDocumentError("The DOCX package is corrupt.")
    except InvalidDocumentError:
        raise
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as exc:
        raise InvalidDocumentError("The DOCX package is corrupt.") from exc


def validate_upload(
    *,
    filename: str | None,
    content_type: str | None,
    data: bytes,
    max_upload_bytes: int,
) -> ValidatedUpload:
    if not filename:
        raise UnsupportedDocumentError("A filename is required.")
    safe_name, extension = _safe_filename(filename)
    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type != _CONTENT_TYPES[extension]:
        raise UnsupportedDocumentError("The file extension and MIME type must match.")
    if len(data) > max_upload_bytes:
        raise UploadTooLargeError("The upload exceeds the configured size limit.")
    if not data:
        raise EmptyDocumentError("The uploaded file is empty.")

    decoded_text: str | None = None
    if extension == ".pdf" and not data.startswith(b"%PDF-"):
        raise InvalidDocumentError("The PDF signature is invalid.")
    if extension == ".docx":
        if not data.startswith(b"PK\x03\x04"):
            raise InvalidDocumentError("The DOCX signature is invalid.")
        _validate_docx_archive(data, max_upload_bytes)
    if extension == ".txt":
        try:
            decoded_text = data.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError as exc:
            raise InvalidDocumentError("TXT files must contain valid UTF-8 text.") from exc
        if not decoded_text.strip():
            raise EmptyDocumentError("The uploaded file contains no usable text.")
        if "\x00" in decoded_text:
            raise InvalidDocumentError("The TXT file contains binary data.")
        if any(
            unicodedata.category(character) == "Cc"
            and character not in "\r\n\t\f"
            for character in decoded_text
        ):
            raise InvalidDocumentError("The TXT file contains binary control characters.")

    return ValidatedUpload(
        data=data,
        filename=safe_name,
        extension=extension,
        content_type=_CONTENT_TYPES[extension],
        decoded_text=decoded_text,
    )


def _extract_pdf(
    data: bytes,
    *,
    max_extracted_characters: int,
    ocr_enabled: bool = False,
    ocr_provider: OCRProvider | None = None,
) -> ExtractedDocument:
    pages: list[ExtractedPage] = []
    text_parts: list[str] = []
    text_length = 0
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            if document.needs_pass:
                raise InvalidDocumentError("Encrypted PDFs are not supported.")
            if document.page_count == 0 or document.page_count > _MAX_PDF_PAGES:
                raise InvalidDocumentError("The PDF has an unsupported page count.")

            catalog = document.pdf_catalog()
            for key in ("OpenAction", "AA", "AcroForm"):
                value_type, _ = document.xref_get_key(catalog, key)
                if value_type.lower() not in ("null", "none"):
                    raise InvalidDocumentError("PDFs with active content are not supported.")
            names_type, names_value = document.xref_get_key(catalog, "Names")
            if names_type.lower() not in ("null", "none") and re.search(
                r"/JavaScript\b", names_value
            ):
                raise InvalidDocumentError("PDFs with active content are not supported.")
            if document.embfile_count() > 0:
                raise InvalidDocumentError(
                    "This PDF contains embedded attachments, which are not accepted. "
                    "Print or save the essay pages as a new PDF and upload that copy. "
                    "Scanned pages will use OCR when OCR is enabled."
                )

            for page_index in range(document.page_count):
                if page_index:
                    text_parts.append("\n\f\n")
                    text_length += 3
                page = document.load_page(page_index)
                page_blocks = [
                    block[4].rstrip("\r\n")
                    for block in page.get_text("blocks", sort=False)
                    if len(block) > 4 and block[4].strip()
                ]
                native_page_text = "\n\n".join(page_blocks)
                extraction_method = "native"
                ocr_confidence = None

                if native_page_text.strip():
                    page_text = native_page_text + "\n"
                elif ocr_enabled:
                    if ocr_provider is None:
                        raise OCRDependencyError(
                            "OCR is enabled but no OCR provider is configured."
                        )
                    try:
                        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2.0, 2.0), alpha=False)
                        image_bytes = pixmap.tobytes("png")
                    except Exception as exc:
                        raise OCRPageRenderError(
                            f"Page {page_index + 1} could not be rendered for OCR."
                        ) from exc
                    try:
                        result = ocr_provider.recognize_page(image_bytes)
                    except OCRDependencyError:
                        raise
                    except OCRPageRenderError:
                        raise
                    except Exception as exc:
                        raise OCRDependencyError(
                            f"OCR failed while processing page {page_index + 1}. "
                            "The OCR model may be unavailable."
                        ) from exc
                    page_text = result.text.strip()
                    if page_text:
                        page_text += "\n"
                        extraction_method = "ocr"
                        ocr_confidence = result.confidence
                else:
                    page_text = ""

                page_start = text_length
                text_parts.append(page_text)
                text_length += len(page_text)
                pages.append(
                    ExtractedPage(
                        page_number=page_index + 1,
                        extracted_char_start=page_start,
                        extracted_char_end=text_length,
                        extraction_method=extraction_method,
                        ocr_confidence=ocr_confidence,
                    )
                )
                if text_length > max_extracted_characters:
                    raise InvalidDocumentError("The extracted text exceeds the processing limit.")
            extracted_text = "".join(text_parts)
            if not extracted_text.strip():
                if ocr_enabled:
                    raise OCRUnreadableError(
                        "OCR could not recognize readable text in this scanned PDF. "
                        "Upload a clearer scan or a typed document."
                    )
                raise EmptyDocumentError(
                    "This appears to be an image-only or unreadable PDF. "
                    "Enable OCR or upload a clearer scan or typed document."
                )
            return ExtractedDocument(
                text=extracted_text,
                pages=pages,
                extractor_name="PyMuPDF+TrOCR" if ocr_enabled and any(
                    page.extraction_method == "ocr" for page in pages
                ) else "PyMuPDF",
                extractor_version=f"{pymupdf.VersionBind}-blocks-v1",
            )
    except InvalidDocumentError:
        raise
    except EmptyDocumentError:
        raise
    except (OCRDependencyError, OCRUnreadableError, OCRPageRenderError):
        raise
    except (pymupdf.FileDataError, OSError, RuntimeError, ValueError) as exc:
        raise InvalidDocumentError("The PDF is corrupt or could not be parsed.") from exc


def _extract_docx(
    data: bytes,
    *,
    max_extracted_characters: int,
) -> ExtractedDocument:
    try:
        document = Document(BytesIO(data))
        blocks: list[str] = []
        for child in document.element.body.iterchildren():
            if isinstance(child, CT_P):
                blocks.append(Paragraph(child, document).text)
            elif isinstance(child, CT_Tbl):
                table = Table(child, document)
                blocks.extend(
                    "\t".join(cell.text.replace("\n", " ") for cell in row.cells)
                    for row in table.rows
                )
        text = "\n\n".join(blocks)
    except (
        PackageNotFoundError,
        XMLSyntaxError,
        zipfile.BadZipFile,
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
    ) as exc:
        raise InvalidDocumentError("The DOCX is corrupt or could not be parsed.") from exc

    if len(text) > max_extracted_characters:
        raise InvalidDocumentError("The extracted text exceeds the processing limit.")
    return ExtractedDocument(
        text=text,
        pages=[
            ExtractedPage(
                page_number=None,
                extracted_char_start=0,
                extracted_char_end=len(text),
            )
        ],
        extractor_name="python-docx",
        extractor_version=f"{docx.__version__}-paragraphs-v1",
    )


def extract_document(
    upload: ValidatedUpload,
    *,
    max_extracted_characters: int = 500_000,
    ocr_enabled: bool = False,
    ocr_provider: OCRProvider | None = None,
) -> ExtractedDocument:
    if max_extracted_characters <= 0:
        raise ValueError("The extracted text limit must be positive.")
    if upload.extension == ".pdf":
        document = _extract_pdf(
            upload.data,
            max_extracted_characters=max_extracted_characters,
            ocr_enabled=ocr_enabled,
            ocr_provider=ocr_provider,
        )
    elif upload.extension == ".docx":
        document = _extract_docx(
            upload.data,
            max_extracted_characters=max_extracted_characters,
        )
    else:
        text = upload.decoded_text or ""
        if len(text) > max_extracted_characters:
            raise InvalidDocumentError("The extracted text exceeds the processing limit.")
        document = ExtractedDocument(
            text=text,
            pages=[
                ExtractedPage(
                    page_number=None,
                    extracted_char_start=0,
                    extracted_char_end=len(text),
                )
            ],
            extractor_name="UTF-8",
            extractor_version="1",
        )

    if not document.text.strip():
        raise EmptyDocumentError("The document contains no extractable text.")
    if any(
        unicodedata.category(character) == "Cc"
        and character not in "\r\n\t\f"
        for character in document.text
    ):
        raise InvalidDocumentError("The extracted text contains invalid control characters.")
    return document
