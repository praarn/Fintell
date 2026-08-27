import uuid
from pathlib import Path

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.bank_profile import BankProfile
from app.models.parse_failure import ParseFailure
from app.models.statement import Statement
from app.models.transaction import Transaction
from app.services import account_service
from app.services.anomaly.service import run_anomaly_detection
from app.services.categorization.service import categorize_statement_transactions
from app.services.categorization.tier3 import categorize_statement_transactions_via_llm
from app.services.parsing.pipeline import parse_statement

settings = get_settings()


class StatementNotFoundError(Exception):
    pass


def _extension_for(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return suffix if suffix in (".csv", ".pdf") else ""


async def upload_and_parse_statement(
    db: AsyncSession,
    user_id: uuid.UUID,
    original_filename: str,
    file_bytes: bytes,
    bank_hint: str | None,
    account_id: uuid.UUID | None = None,
) -> Statement:
    """Stores the raw file locally (plaintext — encryption/signed URLs are
    Phase 8) and runs the full pipeline synchronously: Tier 1 (parsing),
    Tier 2 (rule/fuzzy-match categorization), then Tier 3 (batched LLM
    fallback for whatever's still unresolved).

    Account linking: an explicit account_id is validated and used as-is;
    otherwise a bank_hint auto-provisions a lightweight account (keeps
    older upload calls, and tests, working without requiring the
    account-creation UI first); with neither, the statement is unlinked.
    """
    if account_id is not None:
        account = await account_service.get_owned_account(db, user_id, account_id)
    elif bank_hint:
        account = await account_service.get_or_create_account_for_bank_hint(db, user_id, bank_hint)
    else:
        account = None

    statement = Statement(
        user_id=user_id,
        account_id=account.id if account else None,
        bank_hint=bank_hint,
        original_filename=original_filename,
        file_path="",
        file_type="unknown",
    )
    db.add(statement)
    await db.flush()  # assigns statement.id without committing yet

    storage_dir = Path(settings.upload_storage_dir) / str(user_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / f"{statement.id}{_extension_for(original_filename)}"
    file_path.write_bytes(file_bytes)
    statement.file_path = str(file_path)
    await db.commit()

    await parse_statement(db, statement, file_bytes)

    if account is not None:
        await db.execute(
            update(Transaction)
            .where(Transaction.statement_id == statement.id)
            .values(account_id=account.id)
        )
        await db.commit()

    await categorize_statement_transactions(db, statement.id)
    await categorize_statement_transactions_via_llm(db, statement.id)

    # Phase 6: refit this user's anomaly model now that their history grew.
    # Best-effort — a modelling hiccup must never fail an upload, and users
    # below the min-history threshold simply get a no-op here.
    try:
        await run_anomaly_detection(db, user_id)
    except Exception:  # noqa: BLE001 - deliberately swallowed, see above
        await db.rollback()

    await db.refresh(statement)
    return statement


async def get_owned_statement(
    db: AsyncSession, user_id: uuid.UUID, statement_id: uuid.UUID
) -> Statement:
    statement = await db.scalar(
        select(Statement).where(Statement.id == statement_id, Statement.user_id == user_id)
    )
    if statement is None:
        raise StatementNotFoundError(str(statement_id))
    return statement


def _is_within_storage(path: Path) -> bool:
    """Guard against deleting anything outside the upload directory — the
    stored path is trusted (we wrote it), but this keeps a corrupt row
    from turning a delete into an arbitrary unlink."""
    try:
        storage_root = Path(settings.upload_storage_dir).resolve()
        return storage_root in path.resolve().parents
    except (OSError, RuntimeError):
        return False


async def delete_statement(
    db: AsyncSession, user_id: uuid.UUID, statement_id: uuid.UUID
) -> None:
    """Deletes a statement, its uploaded file, and everything downstream
    of it (transactions cascade to splits and anomaly flags; parse
    failures cascade too — all via ON DELETE CASCADE)."""
    statement = await get_owned_statement(db, user_id, statement_id)

    if statement.file_path:
        file_path = Path(statement.file_path)
        if _is_within_storage(file_path):
            file_path.unlink(missing_ok=True)

    await db.execute(sa_delete(Statement).where(Statement.id == statement_id))
    await db.commit()


def resolve_stored_file(statement: Statement) -> Path:
    """The on-disk path for a statement's uploaded file, if it still
    exists. Raises StatementNotFoundError otherwise (the row can outlive
    the file)."""
    path = Path(statement.file_path) if statement.file_path else None
    if path is None or not path.is_file():
        raise StatementNotFoundError(str(statement.id))
    return path


async def list_statements(db: AsyncSession, user_id: uuid.UUID) -> list[Statement]:
    result = await db.scalars(
        select(Statement).where(Statement.user_id == user_id).order_by(Statement.uploaded_at.desc())
    )
    return list(result)


async def list_transactions(
    db: AsyncSession, user_id: uuid.UUID, statement_id: uuid.UUID
) -> list[Transaction]:
    await get_owned_statement(db, user_id, statement_id)
    result = await db.scalars(
        select(Transaction)
        .where(Transaction.statement_id == statement_id, Transaction.user_id == user_id)
        .order_by(Transaction.row_index)
    )
    return list(result)


async def list_parse_failures(
    db: AsyncSession, user_id: uuid.UUID, statement_id: uuid.UUID
) -> list[ParseFailure]:
    await get_owned_statement(db, user_id, statement_id)
    result = await db.scalars(
        select(ParseFailure)
        .where(ParseFailure.statement_id == statement_id)
        .order_by(ParseFailure.created_at)
    )
    return list(result)


async def compute_stats(db: AsyncSession) -> dict:
    """Bank profiles are global, so these numbers are system-wide, not
    scoped to the calling user — this is the actual "gets better over
    time" claim, and a single user's own upload count wouldn't represent
    it honestly.
    """
    distinct_profiles = await db.scalar(select(func.count()).select_from(BankProfile))

    method_rows = (
        await db.execute(
            select(Statement.parse_method, func.count())
            .where(Statement.parse_method.is_not(None))
            .group_by(Statement.parse_method)
        )
    ).all()
    by_parse_method = dict(method_rows)

    structure_rows = (
        await db.execute(
            select(Statement.detected_structure, func.count())
            .where(Statement.detected_structure.is_not(None))
            .group_by(Statement.detected_structure)
        )
    ).all()
    by_detected_structure = dict(structure_rows)

    status_rows = (
        await db.execute(
            select(Statement.parse_status, func.count()).group_by(Statement.parse_status)
        )
    ).all()
    by_parse_status = dict(status_rows)

    total_processed = sum(by_parse_method.values())
    reuse_count = by_parse_method.get("profile_reuse", 0)
    pct_reuse = (reuse_count / total_processed * 100.0) if total_processed else 0.0

    return {
        "distinct_bank_profiles": distinct_profiles or 0,
        "total_statements_processed": total_processed,
        "pct_profile_reuse": round(pct_reuse, 1),
        "by_parse_method": by_parse_method,
        "by_detected_structure": by_detected_structure,
        "by_parse_status": by_parse_status,
    }
