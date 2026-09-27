from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.passwords import generate_password
from app.core.security import hash_password
from app.models.user import User


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ list

    async def list(
        self,
        *,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[User], int]:
        conditions = []
        if role:
            conditions.append(User.role == role)
        if is_active is not None:
            conditions.append(User.is_active == is_active)
        if search:
            like = f"%{search.strip()}%"
            conditions.append(User.username.ilike(like))

        base = select(User)
        if conditions:
            base = base.where(*conditions)

        total = (
            await self.db.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()

        offset = (page - 1) * size
        items = (
            await self.db.execute(
                base.order_by(User.id.asc()).offset(offset).limit(size)
            )
        ).scalars().all()

        return list(items), total

    # ------------------------------------------------------------------- get

    async def get(self, user_id: int) -> User | None:
        return await self.db.get(User, user_id)

    async def get_by_username(self, username: str) -> User | None:
        q = select(User).where(User.username == username)
        return (await self.db.execute(q)).scalar_one_or_none()

    # ---------------------------------------------------------------- create

    async def create(self, data: dict[str, Any], created_by_id: int) -> User:
        """Создание admin/teacher."""
        role = data.get("role")
        username = data.get("username")
        password = data.get("password")

        if role not in ("admin", "teacher"):
            raise ValueError("only admin or teacher can be created here")
        if not username or not password:
            raise ValueError("username and password are required")

        if await self.get_by_username(username):
            raise ValueError("username already exists")

        user = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            is_active=True,
            created_by_id=created_by_id,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    # ---------------------------------------------------------------- update

    async def update(self, user: User, data: dict[str, Any]) -> User:
        """Частичное обновление с проверками по роли."""
        payload = dict(data)
        new_role: str | None = payload.pop("role", None)
        new_password: str | None = payload.pop("password", None)
        new_is_active: bool | None = payload.pop("is_active", None)

        changed = False

        if new_role is not None:
            if user.role not in ("admin", "teacher"):
                raise ValueError(
                    f"cannot change role of '{user.role}' via this endpoint"
                )
            user.role = new_role
            changed = True

        if new_password is not None:
            user.password_hash = hash_password(new_password)
            changed = True

        if new_is_active is not None:
            user.is_active = new_is_active
            changed = True

        if not changed:
            return user

        await self.db.flush()
        await self.db.refresh(user)
        return user

    # --------------------------------------------------------------- delete

    async def deactivate(self, user: User) -> None:
        """Мягкое удаление: is_active=False."""
        user.is_active = False
        await self.db.flush()

    # --------------------------------------------------------- reset password

    async def reset_password(self, user: User) -> str:
        """Генерирует новый случайный пароль, сохраняет хеш, возвращает пароль."""
        new_password = generate_password(12)
        user.password_hash = hash_password(new_password)
        await self.db.flush()
        return new_password
        # ---------------------------------------------------------------- create trainee
    async def create_trainee(self, data: dict[str, Any], created_by_id: int) -> User:
        """Создание студента преподавателем."""
        username = data.get("username")
        password = data.get("password")
        
        if not username or not password:
            raise ValueError("username and password are required")
        
        if await self.get_by_username(username):
            raise ValueError("username already exists")
        
        user = User(
            username=username,
            password_hash=hash_password(password),
            role="trainee",
            is_active=True,
            created_by_id=created_by_id,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user