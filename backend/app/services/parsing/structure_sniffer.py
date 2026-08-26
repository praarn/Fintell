import io
from dataclasses import dataclass

import pdfplumber


@dataclass
class DetectionResult:
    file_type: str  # "csv" | "pdf"
    detected_structure: str  # clean_csv / pdf_table / pdf_text_no_table / pdf_scan_ocr


def detect_structure(file_bytes: bytes, filename: str, page_sample: int) -> DetectionResult:
    is_pdf = filename.lower().endswith(".pdf") or file_bytes[:4] == b"%PDF"
    if not is_pdf:
        return DetectionResult(file_type="csv", detected_structure="clean_csv")

    has_table = False
    has_text = False
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages[:page_sample]:
            text = (page.extract_text() or "").strip()
            if len(text) > 20:
                has_text = True
            tables = page.extract_tables()
            if any(len(t) >= 2 and len(t[0]) >= 2 for t in tables):
                has_table = True

    if has_table:
        structure = "pdf_table"
    elif has_text:
        structure = "pdf_text_no_table"
    else:
        structure = "pdf_scan_ocr"

    return DetectionResult(file_type="pdf", detected_structure=structure)
