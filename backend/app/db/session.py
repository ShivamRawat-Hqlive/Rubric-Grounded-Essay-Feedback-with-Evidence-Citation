"""SQLAlchemy engine and request-scoped sessions."""

from collections.abc import Generator
from functools import lru_cache

from fastapi import HTTPException, status
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import ConfigurationError, get_settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = get_settings()
    database_url = settings.require_database_url()
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    try:
        session_factory = get_session_factory()
    except ConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not configured.",
        ) from exc

    with session_factory() as session:
        yield session
