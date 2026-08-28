import pytest

from app.core.config import normalize_database_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # already correct — untouched
        (
            "postgresql+asyncpg://finance:finance@localhost:5432/finance",
            "postgresql+asyncpg://finance:finance@localhost:5432/finance",
        ),
        # managed-host shapes
        (
            "postgres://u:p@dpg-abc123-a/finance",
            "postgresql+asyncpg://u:p@dpg-abc123-a/finance",
        ),
        (
            "postgresql://u:p@ep-cool-name.neon.tech/db",
            "postgresql+asyncpg://u:p@ep-cool-name.neon.tech/db",
        ),
        # libpq sslmode -> asyncpg ssl
        (
            "postgres://u:p@host/db?sslmode=require",
            "postgresql+asyncpg://u:p@host/db?ssl=require",
        ),
    ],
)
def test_normalize_database_url(raw: str, expected: str) -> None:
    assert normalize_database_url(raw) == expected
