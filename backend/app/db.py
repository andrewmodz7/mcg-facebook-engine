"""Database setup: async SQLAlchemy engine, session factory, and FastAPI dependency."""

import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

load_dotenv()


def _normalize_async_url(url: str) -> str:
    """Ensure the URL targets the asyncpg driver.

    Railway (and most providers) hand out bare ``postgresql://`` URLs, which
    SQLAlchemy maps to the sync psycopg2 driver. This codebase is async and
    only asyncpg is installed, so coerce the scheme to ``postgresql+asyncpg``.
    """
    if url.startswith("postgresql+"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


DATABASE_URL = _normalize_async_url(os.environ["DATABASE_URL"])

engine = create_async_engine(DATABASE_URL, echo=False, future=True)

async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Base class for ORM model definitions (added later).
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with async_session() as session:
        yield session
