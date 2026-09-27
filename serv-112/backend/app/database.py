from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from inspect import isawaitable
from typing import Any, Awaitable, Callable

import logging

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


logger = logging.getLogger("app.database")

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_AFTER_COMMIT = "after_commit_hooks"
_SKIP_COMMIT = "skip_commit"

SessionHook = Callable[[], Any] | Callable[[], Awaitable[Any]]

def _make_engine(
    *,
    pool_size: int,
    max_overflow: int,
    pool_recycle: int,
    pool_timeout: int,
    echo: bool,
) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=echo,
        pool_pre_ping=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=pool_recycle,
        pool_timeout=pool_timeout,
    )


_engine: AsyncEngine = _make_engine(
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    echo=False,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False,
)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_engine() -> AsyncEngine:
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Актуальный sessionmaker."""
    return AsyncSessionLocal


async def reinit_engine(
    *,
    pool_size: int,
    max_overflow: int,
    pool_recycle: int,
    pool_timeout: int,
    echo: bool = False,
) -> None:
    """Пересоздаёт engine с новыми параметрами пула."""
    global _engine, AsyncSessionLocal
    await _engine.dispose()
    _engine = _make_engine(
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_recycle=pool_recycle,
        pool_timeout=pool_timeout,
        echo=echo,
    )
    AsyncSessionLocal = async_sessionmaker(_engine, expire_on_commit=False)


def on_commit(session: AsyncSession, hook: SessionHook) -> None:
    """Зарегистрировать callback, вызываемый после успешного commit."""
    session.info.setdefault(_AFTER_COMMIT, []).append(hook)


async def _run_after_commit(session: AsyncSession) -> None:
    hooks = session.info.pop(_AFTER_COMMIT, [])
    for hook in hooks:
        try:
            result = hook()
            if isawaitable(result):
                await result
        except Exception:
            logger.exception("after-commit hook failed")


@asynccontextmanager
async def unit_of_work() -> AsyncIterator[AsyncSession]:
    """Одна транзакция на блок кода."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

        if session.info.pop(_SKIP_COMMIT, False):
            # Кто-то снаружи уже разобрался с транзакцией вручную.
            return

        await session.commit()
        await _run_after_commit(session)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: одна транзакция на HTTP-запрос."""
    async with unit_of_work() as session:
        yield session