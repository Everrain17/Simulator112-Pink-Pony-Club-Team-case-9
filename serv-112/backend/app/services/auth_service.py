"""AuthService — тонкая обёртка над UserService для регистрации."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(
        self, username: str, password: str, role: str = "trainee",
    ) -> User:
        """Создать пользователя. Commit — на уровне unit_of_work."""
        user = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user