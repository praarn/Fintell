from datetime import date
from decimal import Decimal

from app.services.parsing.pdf_table_parser import parse_pdf_table
from app.services.parsing.pdf_text_parser import extract_lines_from_pdf, parse_text_lines
from app.services.parsing.structure_sniffer import detect_structure
from tests.conftest import FIXTURES_DIR


def _read(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


def test_pdf_table_detected_and_parsed() -> None:
    data = _read("pdf_table_extractable.pdf")
    detection = detect_structure(data, "pdf_table_extractable.pdf", page_sample=3)
    assert detection.file_type == "pdf"
    assert detection.detected_structure == "pdf_table"

    outcome = parse_pdf_table(data)
    assert len(outcome.rows) == 10
    assert not outcome.failures
    first = outcome.rows[0]
    assert first.date == date(2024, 1, 3)
    assert first.amount == Decimal("-54.23")
    assert first.running_balance == Decimal("4945.77")


def test_pdf_text_no_table_detected_and_parsed() -> None:
    data = _read("pdf_text_no_table.pdf")
    detection = detect_structure(data, "pdf_text_no_table.pdf", page_sample=3)
    assert detection.file_type == "pdf"
    assert detection.detected_structure == "pdf_text_no_table"

    outcome = parse_text_lines(extract_lines_from_pdf(data))
    assert len(outcome.rows) == 10
    assert not outcome.failures
    assert outcome.rows[0].amount == Decimal("-54.23")
