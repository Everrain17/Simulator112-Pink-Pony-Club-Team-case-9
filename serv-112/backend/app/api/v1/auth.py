from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.audit_actions import AuditAction
from app.core.security import (
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.database import get_session
from app.models.user import User
from app.schemas.user import Token, RefreshRequest, MeResponse
from app.api.deps import current_user
from app.services.audit_service import AuditService
from app.services.arm_registry import arm_registry

router = APIRouter()


# Активные сессии обучаемых:
# access_token -> номер ARM
active_sessions: dict[str, int] = {}

# Refresh-токены:
# refresh_token -> номер ARM
refresh_sessions: dict[str, int] = {}


def create_session(user: User) -> Token:
    access_token = create_access_token(user.username)
    refresh_token = create_refresh_token(user.username)

    arm = None

    if user.role == "trainee":
        arm_number = arm_registry.acquire()

        active_sessions[access_token] = arm_number
        refresh_sessions[refresh_token] = arm_number

        arm = f"ARM-{arm_number}"

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_EXP_MIN * 60,
        arm=arm,
    )


@router.post("/login", response_model=Token)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_session),
):
    user = (
        await db.execute(
            select(User).where(User.username == form.username)
        )
    ).scalar_one_or_none()

    audit = AuditService(db)

    if not user or not verify_password(
        form.password,
        user.password_hash,
    ):
        await audit.log_security(
            AuditAction.LOGIN_FAILED,
            username=form.username,
            details={"reason": "bad_credentials"},
        )

        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Bad credentials",
        )

    if not user.is_active:
        await audit.log_security(
            AuditAction.LOGIN_BLOCKED,
            username=user.username,
            details={"reason": "inactive"},
        )

        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "User is deactivated",
        )

    await audit.log(
        category="auth",
        action=AuditAction.LOGIN_SUCCESS,
        user=user,
        level="info",
    )

    return create_session(user)


@router.post("/refresh", response_model=Token)
async def refresh(
    payload: RefreshRequest,
    db: AsyncSession = Depends(get_session),
):
    from jose import JWTError

    audit = AuditService(db)

    try:
        data = decode_token(
            payload.refresh_token,
            expected_type="refresh",
        )
    except JWTError:
        await audit.log_security(
            AuditAction.TOKEN_REFRESH_FAILED,
            details={"reason": "decode_failed"},
        )

        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Invalid refresh token",
        )

    username = data.get("sub")

    user = (
        await db.execute(
            select(User).where(User.username == username)
        )
    ).scalar_one_or_none()

    if not user or not user.is_active:
        await audit.log_security(
            AuditAction.TOKEN_REFRESH_FAILED,
            username=username,
            details={"reason": "user_missing_or_inactive"},
        )

        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "User not found",
        )

    await audit.log(
        category="auth",
        action=AuditAction.TOKEN_REFRESH,
        user=user,
        level="info",
    )

    old_refresh_token = payload.refresh_token

    arm_number = refresh_sessions.get(old_refresh_token)

    access_token = create_access_token(user.username)
    refresh_token = create_refresh_token(user.username)

    arm = None

    if user.role == "trainee" and arm_number is not None:
        refresh_sessions.pop(old_refresh_token, None)

        active_sessions[access_token] = arm_number
        refresh_sessions[refresh_token] = arm_number

        arm = f"ARM-{arm_number}"

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.JWT_ACCESS_EXP_MIN * 60,
        arm=arm,
    )


@router.get("/me", response_model=MeResponse)
async def me(user: User = Depends(current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "created_by_id": user.created_by_id,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "arm": None,
    }


@router.post("/logout")
async def logout(
    request: Request,
    user: User = Depends(current_user),
):
    authorization = request.headers.get("Authorization", "")

    access_token = ""

    if authorization.startswith("Bearer "):
        access_token = authorization[7:]

    arm_number = active_sessions.pop(access_token, None)

    if arm_number is not None:
        arm_registry.release(arm_number)

        for refresh_token, refresh_arm in list(
            refresh_sessions.items()
        ):
            if refresh_arm == arm_number:
                del refresh_sessions[refresh_token]

    return {"ok": True}