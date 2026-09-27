from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import current_user
from app.database import get_session
from app.models.classifier import DialogStage, EmotionalState, InterferenceType
from app.models.user import User
from app.schemas.classifier import (
    ServiceRead,
    IncidentTypeRead,
    DialogStageRead,
    EmotionalStateRead,
    InterferenceTypeRead,
)
from app.services.simcore_client import SimCoreClient, SimCoreError
from fastapi import HTTPException, status

router = APIRouter()



async def _simcore_catalog() -> dict:
    try:
        return await SimCoreClient().classifier()
    except SimCoreError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.get("/services", response_model=list[ServiceRead])
async def list_services(_: User = Depends(current_user)):
    data = await _simcore_catalog()
    return data.get("services", []) or []


@router.get("/incident-types", response_model=list[IncidentTypeRead])
async def list_incident_types(
    service_code: str | None = Query(None),
    _: User = Depends(current_user),
):
    data = await _simcore_catalog()
    rows = data.get("incidentTypes", []) or []
    if service_code:
        needle = service_code.strip().upper()
        rows = [
            row for row in rows
            if str(row.get("mainService") or "").upper() == needle
            or needle in {str(x).upper() for x in (row.get("additionalServices") or [])}
            or str(row.get("ekpCode") or "").upper() == needle
        ]
    return rows


@router.get("/dialog-stages", response_model=list[DialogStageRead])
async def list_dialog_stages(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
):
    q = select(DialogStage).order_by(DialogStage.order_index)
    return (await db.execute(q)).scalars().all()


@router.get("/emotional-states", response_model=list[EmotionalStateRead])
async def list_emotional_states(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
):
    q = select(EmotionalState).order_by(EmotionalState.code)
    return (await db.execute(q)).scalars().all()


@router.get("/interference-types", response_model=list[InterferenceTypeRead])
async def list_interference_types(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
):
    q = select(InterferenceType).order_by(InterferenceType.code)
    return (await db.execute(q)).scalars().all()
