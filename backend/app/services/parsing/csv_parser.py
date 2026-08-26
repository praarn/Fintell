import csv
import io

from app.services.parsing.grid_parser import parse_grid
from app.services.parsing.types import ParseOutcome


def read_csv_grid(file_bytes: bytes) -> list[list[str]]:
    """Stdlib csv rather than pandas here on purpose: real-world statement
    exports are frequently ragged (banner rows with fewer fields than the
    real header/data rows), and pandas' parsers reject ragged rows unless
    told the exact expected column count up front — which we don't know
    yet, that's what header detection is for. csv.reader tolerates ragged
    rows natively, which is exactly the raw material header detection and
    row-parsing below already expect.
    """
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    return [row for row in reader if any(cell.strip() for cell in row)]


def parse_csv(file_bytes: bytes) -> ParseOutcome:
    return parse_grid(read_csv_grid(file_bytes))
