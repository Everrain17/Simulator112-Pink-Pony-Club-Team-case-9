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

import time
import asyncio

router = APIRouter()

# Хранилище активных АРМ для учеников
active_sessions: dict[str, int] = {}

# Хранилище refresh-токенов для учеников
refresh_sessions: dict[str, int] = {}

# Глобальный список ID пользователей, которые сейчас авторизованы в системе
# Ключ: user_id
# Значение: access_token + время последнего heartbeat
currently_logged_in_users: dict[int, dict] = {}

# Через сколько секунд без heartbeat считать сессию потерянной
SESSION_TIMEOUT = 30


def create_session(user: User) -> Token:
    access_token = create_access_token(user.username)
    refresh_token = create_refresh_token(user.username)

    arm = None

    # Фиксируем вход пользователя в глобальном трекере сессий
    currently_logged_in_users[user.id] = {
        "access_token": access_token,
        "last_seen": time.time(),
    }

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

    # 🔥 БЕЗОПАСНАЯ ПРОВЕРКА: Студент защищен. Если он в системе — повторный вход запрещен.
    if user.id in currently_logged_in_users:
        await audit.log_security(
            AuditAction.LOGIN_FAILED,
            username=user.username,
            details={"reason": "already_logged_in"},
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Невозможно войти: данный пользователь уже в системе",
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

    currently_logged_in_users[user.id] = {
        "access_token": access_token,
        "last_seen": time.time(),
    }

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


# ============================================================
# HEARTBEAT
# ============================================================

@router.post("/heartbeat")
async def heartbeat(user: User = Depends(current_user)):
    session = currently_logged_in_users.get(user.id)

    if session is not None:
        session["last_seen"] = time.time()

    return {"ok": True}


# ============================================================
# АВТОМАТИЧЕСКАЯ ОЧИСТКА МЁРТВЫХ СЕССИЙ
# ============================================================

async def cleanup_expired_sessions():
    while True:
        await asyncio.sleep(10)

        now = time.time()

        for user_id, session in list(currently_logged_in_users.items()):
            last_seen = session.get("last_seen", 0)

            if now - last_seen <= SESSION_TIMEOUT:
                continue

            access_token = session.get("access_token")

            currently_logged_in_users.pop(user_id, None)

            arm_number = active_sessions.pop(access_token, None)

            if arm_number is not None:
                arm_registry.release(arm_number)

                for refresh_token, refresh_arm in list(
                    refresh_sessions.items()
                ):
                    if refresh_arm == arm_number:
                        del refresh_sessions[refresh_token]

            print(
                f"[AUTH] Сессия пользователя {user_id} "
                f"истекла по таймауту"
            )


@router.on_event("startup")
async def start_session_cleanup():
    asyncio.create_task(cleanup_expired_sessions())


@router.post("/logout")
async def logout(
    request: Request,
    user: User = Depends(current_user),
):
    authorization = request.headers.get("Authorization", "")

    access_token = ""

    if authorization.startswith("Bearer "):
        access_token = authorization[7:]

    currently_logged_in_users.pop(user.id, None)

    arm_number = active_sessions.pop(access_token, None)

    if arm_number is not None:
        arm_registry.release(arm_number)

        for refresh_token, refresh_arm in list(
            refresh_sessions.items()
        ):
            if refresh_arm == arm_number:
                del refresh_sessions[refresh_token]

    return {"ok": True}