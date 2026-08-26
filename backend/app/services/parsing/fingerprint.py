from dataclasses import dataclass

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank_profile import BankProfile
from app.services.parsing.text_utils import sha256_hex


@dataclass
class ProfileCandidate:
    profile: BankProfile
    match_score: float


async def find_candidate_profile(
    db: AsyncSession,
    structure_type: str,
    fingerprint_text: str,
    fuzzy_threshold: float,
) -> ProfileCandidate | None:
    """Exact-hash fast path, falling back to fuzzy header-similarity match.

    Only returns a *candidate* — the caller is responsible for validating it
    still actually fits the new statement before trusting it (see
    profile_service.py). Bank profiles are global (no user scoping): this
    only ever compares layout metadata, never transaction data.
    """
    fingerprint_hash = sha256_hex(fingerprint_text)

    exact = await db.scalar(
        select(BankProfile).where(
            BankProfile.structure_type == structure_type,
            BankProfile.header_fingerprint_hash == fingerprint_hash,
        )
    )
    if exact is not None:
        return ProfileCandidate(profile=exact, match_score=100.0)

    candidates = (
        await db.scalars(
            select(BankProfile).where(BankProfile.structure_type == structure_type).limit(200)
        )
    ).all()
    if not candidates:
        return None

    choices = {p.id: p.header_fingerprint_normalized for p in candidates}
    match = process.extractOne(fingerprint_text, choices, scorer=fuzz.WRatio)
    if match is None:
        return None

    _, score, profile_id = match
    if score < fuzzy_threshold:
        return None

    profile = next(p for p in candidates if p.id == profile_id)
    return ProfileCandidate(profile=profile, match_score=float(score))
