"""
Одноразовый скрипт наполнения БД тестовыми пользователями.

Перед запуском убедись, что миграции применены:
    alembic upgrade head

Запуск (из backend/, с активированным venv):
    python -m scripts.seed
    # либо:
    python scripts/seed.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import AsyncSessionLocal, get_engine
from app.models.user import User
from app.core.security import hash_password


USERS = [
    ("admin",   "admin",   "admin"),
    ("teacher", "teacher", "teacher"),
    ("trainee", "trainee", "trainee"),
]


async def create_users() -> None:
    async with AsyncSessionLocal() as db:
        for username, password, role in USERS:
            existing = (
                await db.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()

            if existing is not None:
                print(f"skip    {username} (already exists, role={existing.role})")
                continue

            user = User(
                username=username,
                password_hash=hash_password(password),
                role=role,
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"created {username} / {password}  (role={role}, id={user.id})")


async def main() -> None:
    print("→ seeding users...")
    await create_users()
    print("done.")
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(main())