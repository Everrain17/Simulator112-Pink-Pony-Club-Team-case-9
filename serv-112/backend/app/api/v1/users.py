from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role, current_user
from app.core.audit_actions import AuditAction
from app.database import get_session
from app.models.user import User
from app.schemas.user import (
    PasswordResetResponse,
    UserCreate,
    UserPage,
    UserRead,
    UserUpdate,
)
from app.services.admin_guard import ensure_not_last_active_admin
from app.services.audit_service import AuditService
from app.services.user_service import UserService


router = APIRouter()


# ------------------------------------------------------------------- list

@router.get("", response_model=UserPage)
async def list_users(
    search: str | None = Query(None, max_length=64),
    role: str | None = Query(None, pattern="^(admin|teacher|trainee)$"),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_role("admin")),
):
    svc = UserService(db)
    items, total = await svc.list(
        search=search, role=role, is_active=is_active, page=page, size=size
    )
    return UserPage(
        items=[UserRead.model_validate(u) for u in items],
        total=total, page=page, size=size,
        pages=ceil(total / size) if size else 0,
    )

# ---------------------------------------------------------------- create trainee (teacher only)
@router.post("/trainee", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_trainee(
    payload: UserCreate,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("teacher", "admin")),
):
    """Преподаватель создает студента."""
    payload_data = payload.model_dump()
    payload_data["role"] = "trainee"
    
    try:
        user = await UserService(db).create_trainee(payload_data, current.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    
    await AuditService(db).log(
        category="users",
        action=AuditAction.USER_CREATED,
        user=current,
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username, "role": user.role},
    )
    return user

# ---------------------------------------------------------------- list trainees (teacher)
@router.get("/trainees", response_model=UserPage)
async def list_trainees(
    search: str | None = Query(None, max_length=64),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_role("teacher", "admin")),
):
    svc = UserService(db)
    items, total = await svc.list(
        search=search, role="trainee", is_active=is_active, page=page, size=size
    )
    return UserPage(
        items=[UserRead.model_validate(u) for u in items],
        total=total, page=page, size=size,
        pages=ceil(total / size) if size else 0,
    )
# ------------------------------------------------------------------- get

@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_role("admin")),
):
    u = await UserService(db).get(user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return u


# ---------------------------------------------------------------- create

@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("admin")),
):
    try:
        user = await UserService(db).create(payload.model_dump(), current.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    await AuditService(db).log(
        category="users",
        action=AuditAction.USER_CREATED,
        user=current,
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username, "role": user.role},
    )
    return user



# ---------------------------------------------------------------- update

@router.put("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("admin")),
):
    svc = UserService(db)
    user = await svc.get(user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    data = payload.model_dump(exclude_unset=True)

    if current.id == user.id and data.get("is_active") is False:
        await AuditService(db).log(
            category="security",
            action=AuditAction.SELF_DEACTIVATE_BLOCKED,
            user=current,
            level="warning",
            force=True,
            details={"endpoint": "update_user"},
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "cannot deactivate yourself"
        )

    if (
        current.id == user.id
        and data.get("role") is not None
        and user.role == "admin"
        and data["role"] != "admin"
    ):
        await AuditService(db).log(
            category="security",
            action=AuditAction.ADMIN_ACTION_BLOCKED,
            user=current,
            level="warning",
            force=True,
            details={
                "reason": "self_role_demotion",
                "endpoint": "update_user",
                "requested_role": data["role"],
            },
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "cannot demote your own admin role",
        )

    target_is_admin = user.role == "admin" and user.is_active
    demotes = (
        data.get("role") is not None
        and user.role == "admin"
        and data["role"] != "admin"
    )
    deactivates = data.get("is_active") is False and user.is_active
    if target_is_admin and (demotes or deactivates):
        await ensure_not_last_active_admin(
            db,
            exclude_user_id=user.id,
            action="update_user",
            user=current,
        )

    try:
        updated = await svc.update(user, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    await AuditService(db).log(
        category="users",
        action=AuditAction.USER_UPDATED,
        user=current,
        entity_type="user",
        entity_id=updated.id,
        details={"changed_fields": sorted(data.keys())},
    )
    return updated


# ---------------------------------------------------------------- delete

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("admin")),
):
    if current.id == user_id:
        await AuditService(db).log(
            category="security",
            action=AuditAction.SELF_DEACTIVATE_BLOCKED,
            user=current,
            level="warning",
            force=True,
            details={"endpoint": "delete_user"},
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "cannot deactivate yourself"
        )

    svc = UserService(db)
    user = await svc.get(user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    if user.role == "admin" and user.is_active:
        await ensure_not_last_active_admin(
            db,
            exclude_user_id=user.id,
            action="delete_user",
            user=current,
        )

    await svc.deactivate(user)

    await AuditService(db).log(
        category="users",
        action=AuditAction.USER_DEACTIVATED,
        user=current,
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username},
    )


# ----------------------------------------------------------- reset password

@router.post("/{user_id}/reset-password", response_model=PasswordResetResponse)
async def reset_password(
    user_id: int,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(current_user),
):
    if current.role not in ("teacher", "admin"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Forbidden"
        )

    svc = UserService(db)
    user = await svc.get(user_id)

    if not user:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "User not found"
        )

    new_password = await svc.reset_password(user)

    await AuditService(db).log(
        category="users",
        action=AuditAction.PASSWORD_RESET,
        user=current,
        entity_type="user",
        entity_id=user.id,
        details={"username": user.username},
    )

    return PasswordResetResponse(
        new_password=new_password
    )
    
