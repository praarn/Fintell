# backend/app/services/parsing/ — explanation

Tier 1: take the raw bytes of an uploaded statement — any format, any
layout — and produce `Transaction` rows, or a clean `failed_needs_manual`
outcome. This is the most branching subsystem in the app; this file is the
flow. Full rationale is in the root
[`IMPLEMENTATION.md`](../../../../IMPLEMENTATION.md) §7.

## The flow

```
pipeline.parse_statement(db, statement, file_bytes)          ← the only entry point
│
├─ structure_sniffer.detect_structure(bytes, filename)
│     → file_type      : csv | pdf | image
│     → detected_structure : clean_csv | pdf_table | pdf_text_no_table
│                            | pdf_scan_ocr | image_scan_ocr
│
├─ profile_service.parse_statement_file(db, detected_structure, bytes)
│   │
│   │  GRID structures (clean_csv, pdf_table):
│   ├─ read a cell grid  (csv_parser / pdf_table_parser → grid_parser)
│   ├─ fingerprint the header row (fingerprint.py) and look for a saved
│   │     BankProfile with a fuzzy-matching signature
│   │     ├─ hit  + date format still fits → parse_method = "profile_reuse"
│   │     │        (skip straight to known column roles; profile.times_used++)
│   │     └─ miss / stale                  → fall through to cold detection
│   │
│   │  TEXT / OCR structures (pdf_text_no_table, *_scan_ocr):
│   │     always cold — extract lines (pdf_text_parser / ocr_parser), then
│   │     classify as reuse-vs-cold after the fact by fingerprint
│   │
│   └─ cold detection (_cold_parse):
│        column_classifier  → which column is date / description / amount /
│                             debit / credit / balance
│        date handling      → sniff the date format from the values
│        sign_convention    → negative-for-debit vs separate debit/credit
│                             columns vs infer from the balance delta
│        on success, _upsert_profile() saves the resolved mapping as a
│        BankProfile keyed by the header fingerprint → the next statement
│        with this layout is a profile_reuse
│
└─ pipeline persists the outcome:
      parsed rows      → Transaction rows (+ row_count_parsed/failed/total)
      unparseable rows → ParseFailure rows (row_index, raw text, reason_code)
      unresolvable file→ statement.parse_status = "failed_needs_manual"
                         + a ParseFailure with the reason — never an exception
```

## Files

| File | Role |
| --- | --- |
| `pipeline.py` | entry point; drives the run, writes Transaction / ParseFailure, sets `parse_status` |
| `structure_sniffer.py` | bytes + filename → `file_type` + `detected_structure` |
| `profile_service.py` | the reuse-vs-cold decision; `_upsert_profile` after a cold run |
| `fingerprint.py` | header/layout signature + fuzzy candidate lookup |
| `column_classifier.py` | header-row detection + column-role assignment |
| `sign_convention.py` | resolve how debits/credits are expressed |
| `csv_parser.py` | delimited text → cell grid (delimiter + quoting sniff) |
| `pdf_table_parser.py` | ruled-table PDF → cell grid (pdfplumber) |
| `pdf_text_parser.py` | text-layer PDF with no table → lines |
| `ocr_parser.py` | scanned PDF / image → lines (pytesseract; degrades if absent) |
| `grid_parser.py` | shared: cell grid + role map + date format → `ParsedRow`s |
| `text_utils.py` | cell normalisation, amount/date coercion |
| `types.py` | `ParsedRow`, `UnresolvableStructureError`, reason codes |

## Notes

- **Never raises to the caller.** Every failure mode is a persisted row.
  `UnresolvableStructureError` is caught in `pipeline.py` and turned into
  `failed_needs_manual`.
- **`BankProfile` rows are global, not per-user** — they encode column
  layout and date format, nothing account-specific.
- `profile_reuse` means the column roles and date format were genuinely
  taken from the saved profile — not just a bank label reused. `times_used`
  / `times_rejected` on the profile track how well it's holding up.
- OCR is best-effort: with `tesseract` missing, `*_scan_ocr` statements
  fail cleanly rather than crashing the process.
