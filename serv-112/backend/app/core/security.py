"""Безопасность: хеширование пароля, JWT (access + refresh)."""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError

from app.config import settings


# ---------------------------------------------------------------- passwords

def hash_password(password: str) -> str:
    pw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        pw = password.encode("utf-8")[:72]
        return bcrypt.checkpw(pw, hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- tokens

def _make_token(sub: str, token_type: str, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALG)


def create_access_token(sub: str) -> str:
    return _make_token(sub, "access", timedelta(minutes=settings.JWT_ACCESS_EXP_MIN))


def create_refresh_token(sub: str) -> str:
    return _make_token(sub, "refresh", timedelta(days=settings.JWT_REFRESH_EXP_DAYS))


def decode_token(token: str, expected_type: str) -> dict:
    """Возвращает payload или бросает JWTError. Проверяет type."""
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALG])
    if payload.get("type") != expected_type:
        raise JWTError(f"expected token type '{expected_type}'")
    return payload
