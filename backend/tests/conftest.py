from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.database import Base, get_db
from app.main import app

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "statements"

settings = get_settings()

_base_url, _, _db_name = settings.database_url.rpartition("/")
TEST_DATABASE_NAME = f"{_db_name}_test"
TEST_DATABASE_URL = f"{_base_url}/{TEST_DATABASE_NAME}"

# asyncpg's DSN doesn't understand the SQLAlchemy "+asyncpg" driver suffix.
_ASYNCPG_ADMIN_DSN = _base_url.replace("postgresql+asyncpg://", "postgresql://") + "/postgres"


async def _ensure_test_database_exists() -> None:
    conn = await asyncpg.connect(_ASYNCPG_ADMIN_DSN)
    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1", TEST_DATABASE_NAME
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{TEST_DATABASE_NAME}"')
    finally:
        await conn.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    await _ensure_test_database_exists()
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        # Isolate tests from each other regardless of what each test committed.
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(table.delete())
        await session.commit()


@pytest_asyncio.fixture
async def client(db_session) -> AsyncIterator[AsyncClient]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _disable_rate_limiting(monkeypatch):
    """Rate limiting is off by default in the suite — the whole suite
    shares one process (and one in-memory limiter keyed by a single test
    client IP). `test_rate_limit.py` re-enables it explicitly."""
    import app.core.rate_limit as rate_limit_module

    monkeypatch.setattr(rate_limit_module.settings, "rate_limit_enabled", False)
    rate_limit_module.limiter.reset()
    yield
    rate_limit_module.limiter.reset()


@pytest.fixture(autouse=True)
def _isolate_upload_storage(tmp_path, monkeypatch):
    """Every test writes uploaded statement files under a per-test temp
    directory instead of the real backend/uploads/ folder."""
    import app.services.statement_service as statement_service_module

    monkeypatch.setattr(statement_service_module.settings, "upload_storage_dir", str(tmp_path))


@pytest_asyncio.fixture
async def authed_client(client: AsyncClient) -> AsyncClient:
    email = "fixture-user@example.com"
    password = "correct-horse-battery-staple"
    await client.post("/auth/register", json={"email": email, "password": password})
    login = await client.post("/auth/login", json={"email": email, "password": password})
    token = login.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
