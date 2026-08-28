import io
import shutil
from decimal import Decimal

import pytesseract
import pytest
from PIL import Image

from app.services.parsing.ocr_parser import parse_image_ocr, parse_pdf_ocr
from app.services.parsing.structure_sniffer import detect_structure
from app.services.parsing.types import UnresolvableStructureError
from tests.conftest import FIXTURES_DIR


def _read(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def _png_bytes(size: tuple[int, int] = (400, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="PNG")
    return buf.getvalue()


def test_scanned_pdf_detected_as_ocr_structure() -> None:
    data = _read("pdf_scanned_needs_ocr.pdf")
    detection = detect_structure(data, "pdf_scanned_needs_ocr.pdf", page_sample=3)
    assert detection.detected_structure == "pdf_scan_ocr"


@pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="Tesseract binary not installed on this host"
)
def test_real_ocr_extracts_transactions() -> None:
    data = _read("pdf_scanned_needs_ocr.pdf")
    outcome = parse_pdf_ocr(data, min_confidence=40.0)
    assert len(outcome.rows) == 10
    assert not outcome.failures
    assert outcome.rows[0].amount == Decimal("-54.23")


def test_missing_tesseract_binary_degrades_gracefully(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_data", _raise)

    with pytest.raises(UnresolvableStructureError) as exc_info:
        parse_pdf_ocr(_read("pdf_scanned_needs_ocr.pdf"), min_confidence=40.0)

    assert exc_info.value.reason_code == "ocr_unavailable"


def test_low_confidence_ocr_output_is_rejected(monkeypatch) -> None:
    import app.services.parsing.ocr_parser as ocr_parser_module

    monkeypatch.setattr(
        ocr_parser_module, "_ocr_page_lines", lambda image: (["garbled nonsense"], 5.0)
    )

    with pytest.raises(UnresolvableStructureError) as exc_info:
        parse_pdf_ocr(_read("pdf_scanned_needs_ocr.pdf"), min_confidence=40.0)

    assert exc_info.value.reason_code == "ocr_low_confidence"


def test_bare_image_detected_as_image_ocr_structure() -> None:
    detection = detect_structure(_png_bytes(), "statement-photo.png", page_sample=3)
    assert detection.file_type == "image"
    assert detection.detected_structure == "image_scan_ocr"


def test_image_detected_by_extension_even_without_magic_bytes() -> None:
    detection = detect_structure(b"anything at all", "scan.jpg", page_sample=3)
    assert detection.detected_structure == "image_scan_ocr"


def test_image_ocr_parses_transactions_from_recognized_lines(monkeypatch) -> None:
    import app.services.parsing.ocr_parser as ocr_parser_module

    lines = [
        "Date Description Amount",
        "2024-01-03 GROCERY STORE -54.23",
        "2024-01-05 PAYCHECK 1200.00",
        "2024-01-08 COFFEE SHOP -4.75",
    ]
    monkeypatch.setattr(ocr_parser_module, "_ocr_page_lines", lambda image: (lines, 92.0))

    outcome = parse_image_ocr(_png_bytes(), min_confidence=40.0)

    assert len(outcome.rows) == 3
    assert outcome.rows[0].amount == Decimal("-54.23")


def test_unreadable_image_bytes_degrade_gracefully() -> None:
    with pytest.raises(UnresolvableStructureError) as exc_info:
        parse_image_ocr(b"definitely not an image", min_confidence=40.0)

    assert exc_info.value.reason_code == "no_text_extracted"


def test_missing_tesseract_binary_degrades_gracefully_for_images(monkeypatch) -> None:
    def _raise(*args, **kwargs):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr(pytesseract, "image_to_data", _raise)

    with pytest.raises(UnresolvableStructureError) as exc_info:
        parse_image_ocr(_png_bytes(), min_confidence=40.0)

    assert exc_info.value.reason_code == "ocr_unavailable"
