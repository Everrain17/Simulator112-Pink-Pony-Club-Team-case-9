from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.core.audit_actions import AuditAction
from app.database import get_session
from app.models.user import User
from app.services.audit_service import AuditService

oauth2 = OAuth2PasswordBearer(tokenUrl=f"{settings.API_PREFIX}/auth/login")


async def current_user(
    token: str = Depends(oauth2),
    db: AsyncSession = Depends(get_session),
) -> User:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
        if payload.get("type") != "access":
            raise JWTError("wrong token type")
        username = payload["sub"]
    except (JWTError, KeyError):
        await AuditService(db).log_security(
            AuditAction.INVALID_TOKEN,
            details={"reason": "decode_failed"},
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    user = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()

    if not user:
        await AuditService(db).log_security(
            AuditAction.INVALID_TOKEN,
            username=username,
            details={"reason": "user_not_found"},
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    if not user.is_active:
        await AuditService(db).log_security(
            AuditAction.INVALID_TOKEN,
            username=username,
            details={"reason": "user_inactive"},
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inactive user")

    return user


def require_role(*roles: str):
    async def _checker(
        user: User = Depends(current_user),
        db: AsyncSession = Depends(get_session),
    ) -> User:
        if user.role not in roles:
            await AuditService(db).log(
                category="security",
                action=AuditAction.ACCESS_DENIED,
                user=user,
                level="warning",
                details={"required": list(roles), "actual": user.role},
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Forbidden")
        return user
    return _checker