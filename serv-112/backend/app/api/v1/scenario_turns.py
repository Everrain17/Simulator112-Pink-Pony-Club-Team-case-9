from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, require_role
from app.core.audit_actions import AuditAction
from app.database import get_session
from app.models.user import User
from app.schemas.scenario_turn import (
    TurnCreate,
    TurnRead,
    TurnReorder,
    TurnUpdate,
)
from app.services.admin_guard import ensure_no_active_session
from app.services.audit_service import AuditService
from app.services.scenario_service import ScenarioService
from app.services.scenario_turn_service import ScenarioTurnService


router = APIRouter()


async def _ensure_scenario(db: AsyncSession, scenario_id: int):
    s = await ScenarioService(db).get(scenario_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Scenario not found")
    return s


@router.get("/{scenario_id}/turns", response_model=list[TurnRead])
async def list_turns(
    scenario_id: int,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
):
    await _ensure_scenario(db, scenario_id)
    return await ScenarioTurnService(db).list_for_scenario(scenario_id)


@router.post(
    "/{scenario_id}/turns",
    response_model=TurnRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_turn(
    scenario_id: int,
    payload: TurnCreate,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("teacher", "admin")),
):
    await _ensure_scenario(db, scenario_id)
    await ensure_no_active_session(
        db, scenario_id=scenario_id, action="create_turn", user=current,
    )

    turn = await ScenarioTurnService(db).create(scenario_id, payload.model_dump())

    await AuditService(db).log(
        category="scenarios",
        action=AuditAction.TURN_CREATED,
        user=current,
        entity_type="turn",
        entity_id=turn.id,
        details={
            "scenario_id": scenario_id,
            "turn_index": turn.turn_index,
            "speaker": turn.speaker,
        },
    )
    return turn

@router.put("/{scenario_id}/turns/reorder", response_model=list[TurnRead])
async def reorder_turns(
    scenario_id: int,
    payload: TurnReorder,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("teacher", "admin")),
):
    await _ensure_scenario(db, scenario_id)
    await ensure_no_active_session(
        db, scenario_id=scenario_id, action="reorder_turns", user=current,
    )

    try:
        result = await ScenarioTurnService(db).reorder(scenario_id, payload.ids)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    await AuditService(db).log(
        category="scenarios",
        action=AuditAction.TURN_REORDERED,
        user=current,
        entity_type="scenario",
        entity_id=scenario_id,
        details={"count": len(payload.ids), "ids": payload.ids},
        level="info",
    )
    return result


@router.put("/{scenario_id}/turns/{turn_id}", response_model=TurnRead)
async def update_turn(
    scenario_id: int,
    turn_id: int,
    payload: TurnUpdate,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("teacher", "admin")),
):
    svc = ScenarioTurnService(db)
    turn = await svc.get(scenario_id, turn_id)
    if not turn:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Turn not found")

    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not data:
        return turn

    await ensure_no_active_session(
        db, scenario_id=scenario_id, action="update_turn", user=current,
    )

    updated = await svc.update(turn, data)

    await AuditService(db).log(
        category="scenarios",
        action=AuditAction.TURN_UPDATED,
        user=current,
        entity_type="turn",
        entity_id=updated.id,
        details={
            "scenario_id": scenario_id,
            "changed_fields": sorted(data.keys()),
        },
    )
    return updated


@router.delete(
    "/{scenario_id}/turns/{turn_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_turn(
    scenario_id: int,
    turn_id: int,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("teacher", "admin")),
):
    svc = ScenarioTurnService(db)
    turn = await svc.get(scenario_id, turn_id)
    if not turn:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Turn not found")

    await ensure_no_active_session(
        db, scenario_id=scenario_id, action="delete_turn", user=current,
    )

    await svc.delete(turn)

    await AuditService(db).log(
        category="scenarios",
        action=AuditAction.TURN_DELETED,
        user=current,
        entity_type="turn",
        entity_id=turn_id,
        details={"scenario_id": scenario_id, "turn_index": turn.turn_index},
    )