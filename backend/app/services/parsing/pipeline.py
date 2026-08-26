from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.parse_failure import ParseFailure
from app.models.statement import Statement
from app.models.transaction import Transaction
from app.services.parsing import profile_service
from app.services.parsing.structure_sniffer import detect_structure
from app.services.parsing.types import UnresolvableStructureError

settings = get_settings()


async def parse_statement(db: AsyncSession, statement: Statement, file_bytes: bytes) -> None:
    """Runs the full Tier 1 pipeline for one uploaded statement and mutates
    `statement` in place with the outcome, persisting Transaction and
    ParseFailure rows along the way. Never raises — any unresolvable
    structure becomes a `failed_needs_manual` statement with a logged
    ParseFailure, never a silent drop or a 500.
    """
    detection = detect_structure(
        file_bytes, statement.original_filename, settings.pdf_structure_detection_page_sample
    )
    statement.file_type = detection.file_type
    statement.detected_structure = detection.detected_structure

    try:
        result = await profile_service.parse_statement_file(
            db, detection.detected_structure, file_bytes
        )
    except UnresolvableStructureError as exc:
        statement.parse_status = "failed_needs_manual"
        statement.parse_method = None
        statement.error_message = exc.reason
        statement.row_count_total = 0
        statement.row_count_parsed = 0
        statement.row_count_failed = 0
        db.add(
            ParseFailure(
                statement_id=statement.id,
                row_index=None,
                raw_line_text="",
                reason_code=exc.reason_code,
                reason=exc.reason,
            )
        )
        await db.commit()
        return

    outcome = result.outcome
    statement.bank_profile_id = result.profile.id
    statement.parse_method = result.parse_method
    statement.bank_profile_match_score = result.match_score

    for row in outcome.rows:
        db.add(
            Transaction(
                statement_id=statement.id,
                user_id=statement.user_id,
                raw_merchant=row.description,
                amount=row.amount,
                date=row.date,
                running_balance=row.running_balance,
                raw_line_text=row.raw_line_text,
                row_index=row.row_index,
            )
        )

    for failure in outcome.failures:
        db.add(
            ParseFailure(
                statement_id=statement.id,
                row_index=failure.row_index,
                raw_line_text=failure.raw_line_text,
                reason_code=failure.reason_code,
                reason=failure.reason,
            )
        )

    row_level_failures = [f for f in outcome.failures if f.row_index is not None]
    parsed = len(outcome.rows)
    failed = len(row_level_failures)

    statement.row_count_total = parsed + failed
    statement.row_count_parsed = parsed
    statement.row_count_failed = failed

    if parsed == 0:
        statement.parse_status = "failed_needs_manual"
        statement.error_message = "no transactions could be parsed from this statement"
    elif failed > 0 or outcome.warnings:
        statement.parse_status = "parsed_with_warnings"
    else:
        statement.parse_status = "parsed_clean"

    await db.commit()
