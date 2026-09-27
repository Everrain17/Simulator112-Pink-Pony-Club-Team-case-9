from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, require_role
from app.core.audit_actions import AuditAction
from app.database import get_session
from app.models.user import User
from app.schemas.action_trace import (
    ActionTraceCreate,
    ActionTracePage,
    ActionTraceRead,
    ActionTraceUpdate,
)
from app.services.action_trace_service import ActionTraceService
from app.services.audit_service import AuditService


router = APIRouter()


# ------------------------------------------------------------------- list

@router.get("", response_model=ActionTracePage)
async def list_traces(
    scenario_id: int | None = Query(None),
    operator_id: int | None = Query(None),
    is_reference: bool | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
):
    svc = ActionTraceService(db)
    items, total = await svc.list_traces(
        scenario_id=scenario_id,
        operator_id=operator_id,
        is_reference=is_reference,
        page=page,
        size=size,
    )
    return ActionTracePage(
        items=[ActionTraceRead.model_validate(t) for t in items],
        total=total, page=page, size=size,
        pages=ceil(total / size) if size else 0,
    )


# ------------------------------------------------------------------- get

@router.get("/{trace_id}", response_model=ActionTraceRead)
async def get_trace(
    trace_id: int,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
):
    t = await ActionTraceService(db).get(trace_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trace not found")
    return t


# ---------------------------------------------------------------- create

@router.post("", response_model=ActionTraceRead, status_code=status.HTTP_201_CREATED)
async def create_trace(
    payload: ActionTraceCreate,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("teacher", "admin")),
):
    trace = await ActionTraceService(db).create(payload.model_dump())

    await AuditService(db).log(
        category="traces",
        action=AuditAction.TRACE_CREATED,
        user=current,
        entity_type="trace",
        entity_id=trace.id,
        details={
            "scenario_id": trace.scenario_id,
            "steps": len(trace.actions or []),
            "is_reference": trace.is_reference,
        },
    )
    return trace


# ---------------------------------------------------------------- update

@router.put("/{trace_id}", response_model=ActionTraceRead)
async def update_trace(
    trace_id: int,
    payload: ActionTraceUpdate,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("teacher", "admin")),
):
    svc = ActionTraceService(db)
    trace = await svc.get(trace_id)
    if not trace:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trace not found")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        return trace

    updated = await svc.update(trace, data)

    await AuditService(db).log(
        category="traces",
        action=AuditAction.TRACE_UPDATED,
        user=current,
        entity_type="trace",
        entity_id=updated.id,
        details={
            "changed_fields": sorted(data.keys()),
            "steps_replaced": "actions" in data,
        },
    )
    return updated


# ---------------------------------------------------------------- delete

@router.delete("/{trace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trace(
    trace_id: int,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("admin")),
):
    svc = ActionTraceService(db)
    trace = await svc.get(trace_id)
    if not trace:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trace not found")

    await svc.delete(trace)

    await AuditService(db).log(
        category="traces",
        action=AuditAction.TRACE_DELETED,
        user=current,
        entity_type="trace",
        entity_id=trace_id,
    )