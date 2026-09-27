"""
Alembic environment для async SQLAlchemy.

- URL берётся из app.config.settings (читает .env).
- target_metadata — из app.database.Base.
- Все модели импортируются, чтобы autogenerate видел таблицы.
"""

import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# --- 1. подтягиваем настройки и Base ---
from app.config import settings
from app.database import Base

# --- 2. импортируем ВСЕ модели, чтобы они зарегистрировались в Base.metadata ---
from app.models.user import User            # noqa: F401
from app.models.scenario import Scenario    # noqa: F401
from app.models.session import TrainingSession  # noqa: F401

# Alembic Config
config = context.config

# Подставляем URL из .env в конфиг Alembic
config.set_main_option("sqlalchemy.url", settings.database_url)

# Логирование из alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Метаданные для autogenerate
target_metadata = Base.metadata


# --------------------------------------------------------------------- offline

def run_migrations_offline() -> None:
    """Генерация SQL-скрипта без подключения к БД."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# --------------------------------------------------------------------- online

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Онлайн-миграции через async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()