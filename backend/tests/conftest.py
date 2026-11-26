"""Shared database and HTTP fixtures."""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.core.rate_limit import AuthRateLimitMiddleware
from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture
def test_engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def test_session_factory(test_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=test_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret_key=SecretStr("test-only-signing-key-not-for-production-32-bytes"),
        jwt_access_token_expire_minutes=15,
        file_storage_dir=tmp_path,
        llm_provider=None,
        openai_api_key=None,
        llm_request_timeout_seconds=1,
        max_evaluation_chars=30_000,
    )


@pytest_asyncio.fixture
async def client(
    test_session_factory: sessionmaker[Session],
    test_settings: Settings,
) -> AsyncIterator[AsyncClient]:
    def reset_rate_limiter() -> None:
        middleware = app.middleware_stack
        while middleware is not None:
            if isinstance(middleware, AuthRateLimitMiddleware):
                middleware.reset()
                return
            middleware = getattr(middleware, "app", None)

    reset_rate_limiter()

    def override_get_db() -> Iterator[Session]:
        with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_settings] = lambda: test_settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    reset_rate_limiter()
