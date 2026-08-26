import shutil
from decimal import Decimal

import pytesseract
import pytest

from app.services.parsing.ocr_parser import parse_pdf_ocr
from app.services.parsing.structure_sniffer import detect_structure
from app.services.parsing.types import UnresolvableStructureError
from tests.conftest import FIXTURES_DIR


def _read(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


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
