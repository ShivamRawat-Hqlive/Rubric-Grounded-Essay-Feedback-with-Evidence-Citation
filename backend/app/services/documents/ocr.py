"""Optional OCR providers for scanned PDF pages."""

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Protocol


class OCRDependencyError(ValueError):
    """Raised when optional OCR dependencies or model files are unavailable."""


class OCRUnreadableError(ValueError):
    """Raised when OCR produces no usable text for a scanned page."""


class OCRPageRenderError(ValueError):
    """Raised when a PDF page cannot be rendered for OCR."""


@dataclass(frozen=True)
class OCRPageResult:
    text: str
    confidence: float | None = None


class OCRProvider(Protocol):
    def recognize_page(self, image_bytes: bytes) -> OCRPageResult:
        ...


@lru_cache(maxsize=1)
def _load_trocr(model_id: str, device: str):
    try:
        import torch
        from PIL import Image, ImageOps
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    except ImportError as exc:
        raise OCRDependencyError(
            "OCR dependencies are missing. Install requirements-ocr.txt "
            "and retry the upload."
        ) from exc

    try:
        selected_device = (
            torch.device("cuda") if device.lower() == "cuda" and torch.cuda.is_available()
            else torch.device("cpu")
        )
        processor = TrOCRProcessor.from_pretrained(model_id)
        model = VisionEncoderDecoderModel.from_pretrained(model_id)
        model.to(selected_device)
        model.eval()
    except Exception as exc:
        raise OCRDependencyError(
            f"The TrOCR model '{model_id}' could not be loaded. "
            "Check the model cache or network connection."
        ) from exc
    return processor, model, selected_device, torch, Image, ImageOps


class TrOCRProvider:
    """Lazy, process-wide cached Microsoft TrOCR handwritten recognizer."""

    def __init__(self, model_id: str = "microsoft/trocr-base-handwritten", device: str = "cpu"):
        self.model_id = model_id
        self.device = device

    def recognize_page(self, image_bytes: bytes) -> OCRPageResult:
        processor, model, selected_device, torch, Image, ImageOps = _load_trocr(
            self.model_id, self.device
        )
        try:
            source = Image.open(BytesIO(image_bytes)).convert("RGB")
        except Exception as exc:
            raise OCRPageRenderError("The scanned page could not be prepared for OCR.") from exc

        grayscale = ImageOps.autocontrast(source.convert("L"))
        grayscale = grayscale.resize(
            (max(1, grayscale.width * 2), max(1, grayscale.height * 2))
        )
        line_images = _detect_text_lines(grayscale)
        if not line_images:
            return OCRPageResult(text="")

        recognized_lines: list[str] = []
        for line_image in line_images:
            pixel_values = processor(images=line_image.convert("RGB"), return_tensors="pt").pixel_values
            pixel_values = pixel_values.to(selected_device)
            with torch.no_grad():
                generated_ids = model.generate(pixel_values)
            text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
            if text:
                recognized_lines.append(text)

        return OCRPageResult(text="\n".join(recognized_lines))


def _detect_text_lines(grayscale) -> list:
    """Detect horizontal text bands using a projection profile, then crop each line."""
    threshold = grayscale.point(lambda value: 255 if value > 210 else 0)
    pixels = threshold.load()
    foreground = []
    for y in range(threshold.height):
        foreground.append(
            sum(1 for x in range(threshold.width) if pixels[x, y] == 0)
        )

    active = [count >= max(2, threshold.width // 500) for count in foreground]
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    for index, is_active in enumerate(active):
        if is_active and start is None:
            start = index
        elif not is_active and start is not None:
            end = index
            if end - start >= 2:
                ranges.append((start, end))
            start = None
    if start is not None:
        ranges.append((start, threshold.height))

    merged: list[tuple[int, int]] = []
    for line_start, line_end in ranges:
        if merged and line_start - merged[-1][1] <= max(8, threshold.height // 100):
            merged[-1] = (merged[-1][0], line_end)
        else:
            merged.append((line_start, line_end))

    padding_y = max(4, threshold.height // 200)
    padding_x = max(4, threshold.width // 200)
    crops = []
    for line_start, line_end in merged:
        left = 0
        right = threshold.width
        top = max(0, line_start - padding_y)
        bottom = min(threshold.height, line_end + padding_y)
        crops.append(
            grayscale.crop(
                (
                    max(0, left - padding_x),
                    top,
                    min(threshold.width, right + padding_x),
                    bottom,
                )
            )
        )
    return crops
