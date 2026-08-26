import io

import pdfplumber

from app.services.parsing.constants import REASON_NO_REQUIRED_COLUMNS_RESOLVED
from app.services.parsing.grid_parser import parse_grid
from app.services.parsing.types import ParseOutcome, UnresolvableStructureError


def extract_largest_table(file_bytes: bytes) -> list[list[str]] | None:
    best_grid: list[list[str]] | None = None
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                grid = [[(cell or "").strip() for cell in row] for row in table]
                if best_grid is None or len(grid) > len(best_grid):
                    best_grid = grid
    return best_grid


def parse_pdf_table(file_bytes: bytes) -> ParseOutcome:
    """Extracts the single largest ruled table in the document and reuses
    the same header-detection/column-classification/row-parsing pipeline as
    CSV. Statements spanning multiple pages/tables are not stitched
    together in this phase — a known simplification, not required by the
    fixture set.
    """
    grid = extract_largest_table(file_bytes)
    if not grid:
        raise UnresolvableStructureError(
            REASON_NO_REQUIRED_COLUMNS_RESOLVED, "no extractable table found in PDF"
        )
    return parse_grid(grid)
