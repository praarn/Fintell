import pypdfium2 as pdfium
import pytesseract

from app.services.parsing.constants import REASON_OCR_LOW_CONFIDENCE, REASON_OCR_UNAVAILABLE
from app.services.parsing.pdf_text_parser import parse_text_lines
from app.services.parsing.types import ParseOutcome, UnresolvableStructureError

RENDER_SCALE = 300 / 72  # ~300 DPI


def _ocr_page_lines(pil_image) -> tuple[list[str], float]:
    """Reconstructs text lines from OCR word boxes by clustering on vertical
    position rather than trusting Tesseract's own block/line segmentation —
    a statement with wide gaps between date/description/amount columns can
    get misread by Tesseract as separate layout blocks, splitting one
    logical line across multiple "line_num" groups.
    """
    data = pytesseract.image_to_data(pil_image, output_type=pytesseract.Output.DICT)
    words: list[tuple[int, int, int, str]] = []
    confidences: list[float] = []

    for i in range(len(data["text"])):
        word = data["text"][i].strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf >= 0:
            confidences.append(conf)
        if not word:
            continue
        words.append((data["top"][i], data["left"][i], data["height"][i], word))

    words.sort(key=lambda w: (w[0], w[1]))

    clusters: list[list[tuple[int, int, str]]] = []
    for top, left, height, word in words:
        tolerance = max(height, 10) * 0.6
        target = next((c for c in clusters if abs(top - c[0][0]) <= tolerance), None)
        if target is None:
            clusters.append([(top, left, word)])
        else:
            target.append((top, left, word))

    lines = [
        " ".join(word for _, _, word in sorted(cluster, key=lambda t: t[1])) for cluster in clusters
    ]
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return lines, mean_confidence


def parse_pdf_ocr(file_bytes: bytes, min_confidence: float) -> ParseOutcome:
    """Renders every page to an image and OCRs it. Never raises a raw
    exception up to the API layer: a missing Tesseract binary or
    low-confidence OCR output both degrade to an UnresolvableStructureError,
    which the pipeline turns into a normal failed_needs_manual response.
    """
    try:
        pdf = pdfium.PdfDocument(file_bytes)
        all_lines: list[str] = []
        confidences: list[float] = []
        for page in pdf:
            bitmap = page.render(scale=RENDER_SCALE)
            pil_image = bitmap.to_pil()
            lines, confidence = _ocr_page_lines(pil_image)
            all_lines.extend(lines)
            confidences.append(confidence)
    except pytesseract.TesseractNotFoundError as exc:
        raise UnresolvableStructureError(
            REASON_OCR_UNAVAILABLE,
            "Tesseract OCR binary not found on this host; install tesseract-ocr to "
            "enable scanned-PDF parsing.",
        ) from exc

    overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    if not all_lines or overall_confidence < min_confidence:
        raise UnresolvableStructureError(
            REASON_OCR_LOW_CONFIDENCE,
            f"OCR mean confidence {overall_confidence:.1f} is below the "
            f"{min_confidence} threshold — not attempting to parse likely-garbage text",
        )

    return parse_text_lines(all_lines)
