import io
from dataclasses import dataclass

import pdfplumber

# Leading bytes that identify raster-image formats, so a photographed or
# scanned statement uploaded as a bare image (not wrapped in a PDF) is
# routed to the same OCR path as a scanned PDF.
_IMAGE_MAGIC: tuple[bytes, ...] = (
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"\xff\xd8\xff",  # JPEG
    b"GIF87a",
    b"GIF89a",
    b"BM",  # BMP
    b"II*\x00",  # TIFF (little-endian)
    b"MM\x00*",  # TIFF (big-endian)
)
_IMAGE_EXTENSIONS: tuple[str, ...] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".jpe",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".webp",
    ".heic",
    ".heif",
)


@dataclass
class DetectionResult:
    file_type: str  # "csv" | "pdf" | "image"
    detected_structure: str
    # clean_csv / pdf_table / pdf_text_no_table / pdf_scan_ocr / image_scan_ocr


def _looks_like_image(file_bytes: bytes, name: str) -> bool:
    if name.endswith(_IMAGE_EXTENSIONS):
        return True
    if file_bytes[:12].startswith(b"RIFF") and file_bytes[8:12] == b"WEBP":
        return True
    return any(file_bytes.startswith(magic) for magic in _IMAGE_MAGIC)


def detect_structure(file_bytes: bytes, filename: str, page_sample: int) -> DetectionResult:
    name = (filename or "").lower()

    is_pdf = name.endswith(".pdf") or file_bytes[:4] == b"%PDF"
    if not is_pdf:
        if _looks_like_image(file_bytes, name):
            return DetectionResult(file_type="image", detected_structure="image_scan_ocr")
        # Everything else — CSV/TSV/TXT and any unrecognized upload — is fed
        # to the delimited-grid parser, which fails honestly (a logged
        # ParseFailure, never a crash) when the bytes aren't tabular.
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
