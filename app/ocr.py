"""Rasterize every PDF page, then run real OCR; never reads PDF text layers."""

import io
import threading
import warnings

import pypdfium2 as pdfium
import pytesseract
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import Settings
from app.models import OCRPage, PipelineError

# PDFium is not thread-safe. Serialize its use within this process.
PDF_LOCK = threading.Lock()
MAX_PIXELS = 16_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def _check_size(width: float, height: float):
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise PipelineError("image_too_large", "Page dimensions exceed the configured limit.", 413)


def _ocr_image(image: Image.Image, settings: Settings) -> str:
    image = ImageOps.autocontrast(ImageOps.grayscale(ImageOps.exif_transpose(image)))
    try:
        return pytesseract.image_to_string(
            image, lang="eng", config="--psm 6", timeout=settings.ocr_timeout_seconds
        ).strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise PipelineError("ocr_unavailable", "Install Tesseract or use Docker.", 503) from exc
    except pytesseract.TesseractError as exc:
        raise PipelineError("ocr_failed", "Tesseract could not process this document.") from exc
    except RuntimeError as exc:
        raise PipelineError("ocr_timeout", "OCR timed out. Try a smaller document.", 504) from exc


def read_pages(data: bytes, settings: Settings) -> list[OCRPage]:
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    pages: list[OCRPage] = []
    if data.startswith(b"%PDF-"):
        try:
            # Keep the lock until page/bitmap resources have been released.
            with PDF_LOCK, pdfium.PdfDocument(data) as document:
                if len(document) > settings.max_pages:
                    raise PipelineError("too_many_pages", "PDF exceeds the configured page limit.", 413)
                for index in range(len(document)):
                    page = document[index]
                    try:
                        width, height = page.get_size()
                        _check_size(width * 2, height * 2)
                        bitmap = page.render(scale=2)
                        try:
                            image = bitmap.to_pil().copy()
                        finally:
                            bitmap.close()
                        pages.append(OCRPage(number=index + 1, text=_ocr_image(image, settings)))
                        image.close()
                    finally:
                        page.close()
        except PipelineError:
            raise
        except Exception as exc:
            raise PipelineError("invalid_pdf", "PDF is damaged, encrypted, or unsupported.") from exc
    else:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    if image.format not in {"PNG", "JPEG"}:
                        raise PipelineError("unsupported_file", "Use PDF, PNG, or JPEG.", 415)
                    _check_size(*image.size)
                    image.load()
                    pages.append(OCRPage(number=1, text=_ocr_image(image, settings)))
        except PipelineError:
            raise
        except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise PipelineError("image_too_large", "Image exceeds the pixel limit.", 413) from exc
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise PipelineError("unsupported_file", "Use a readable PDF, PNG, or JPEG.", 415) from exc
    count = sum(len(page.text) for page in pages)
    if count < 10:
        raise PipelineError("no_readable_text", "No readable text was found. Try a clearer scan.")
    if count > settings.max_ocr_chars:
        raise PipelineError("text_too_long", "OCR text exceeds the configured model-input limit.", 413)
    return pages

