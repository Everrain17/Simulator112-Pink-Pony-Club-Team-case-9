from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, require_role
from app.core.audit_actions import AuditAction
from app.database import get_session
from app.models.user import User
from app.schemas.scenario import (
    ScenarioCreate,
    ScenarioPage,
    ScenarioRead,
    ScenarioUpdate,
)
from app.services.admin_guard import ensure_no_active_session
from app.services.audit_service import AuditService
from app.services.scenario_service import ScenarioService


router = APIRouter()


# --------------------------------------------------------------- read list

@router.get("", response_model=ScenarioPage)
async def list_scenarios(
    search: str | None = Query(None, max_length=255),
    difficulty: int | None = Query(None, ge=1, le=5),
    is_active: bool | None = Query(None),
    author_id: int | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
):
    svc = ScenarioService(db)
    items, total = await svc.list(
        search=search,
        difficulty=difficulty,
        is_active=is_active,
        author_id=author_id,
        page=page,
        size=size,
    )
    return ScenarioPage(
        items=[ScenarioRead.model_validate(s) for s in items],
        total=total,
        page=page,
        size=size,
        pages=ceil(total / size) if size else 0,
    )


# --------------------------------------------------------------- read one

@router.get("/{scenario_id}", response_model=ScenarioRead)
async def get_scenario(
    scenario_id: int,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
):
    s = await ScenarioService(db).get(scenario_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scenario not found")
    return s


# ---------------------------------------------------------------- create

@router.post("", response_model=ScenarioRead, status_code=status.HTTP_201_CREATED)
async def create_scenario(
    payload: ScenarioCreate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_role("teacher", "admin")),
):
    scenario = await ScenarioService(db).create(payload.model_dump(), user.id)

    await AuditService(db).log(
        category="scenarios",
        action=AuditAction.SCENARIO_CREATED,
        user=user,
        entity_type="scenario",
        entity_id=scenario.id,
        details={"title": scenario.title, "difficulty": scenario.difficulty},
    )
    return scenario


# ---------------------------------------------------------------- update

@router.put("/{scenario_id}", response_model=ScenarioRead)
async def update_scenario(
    scenario_id: int,
    payload: ScenarioUpdate,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("teacher", "admin")),
):
    svc = ScenarioService(db)
    s = await svc.get(scenario_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scenario not found")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        return s

    await ensure_no_active_session(
        db, scenario_id=scenario_id, action="update_scenario", user=current,
    )

    updated = await svc.update(s, data)

    await AuditService(db).log(
        category="scenarios",
        action=AuditAction.SCENARIO_UPDATED,
        user=current,
        entity_type="scenario",
        entity_id=updated.id,
        details={"changed_fields": sorted(data.keys())},
    )
    return updated


# ---------------------------------------------------------------- delete

@router.delete("/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scenario(
    scenario_id: int,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("admin")),
):
    svc = ScenarioService(db)
    s = await svc.get(scenario_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scenario not found")

    await ensure_no_active_session(
        db, scenario_id=scenario_id, action="delete_scenario", user=current,
    )

    await svc.deactivate(s)

    await AuditService(db).log(
        category="scenarios",
        action=AuditAction.SCENARIO_DEACTIVATED,
        user=current,
        entity_type="scenario",
        entity_id=s.id,
        details={"title": s.title},
    )