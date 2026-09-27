from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, require_role
from app.core.audit_actions import AuditAction
from app.database import get_session
from app.models.user import User
from app.schemas.incident_card import (
    IncidentCardCreate,
    IncidentCardPage,
    IncidentCardRead,
    IncidentCardUpdate,
)
from app.services.audit_service import AuditService
from app.services.incident_card_service import IncidentCardService


router = APIRouter()


# ------------------------------------------------------------------- list

@router.get("", response_model=IncidentCardPage)
async def list_cards(
    search: str | None = Query(None, max_length=255),
    incident_type_code: str | None = Query(None),
    source: str | None = Query(None, pattern="^(synthetic|real|import)$"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
):
    svc = IncidentCardService(db)
    items, total = await svc.list(
        search=search,
        incident_type_code=incident_type_code,
        source=source,
        page=page,
        size=size,
    )
    return IncidentCardPage(
        items=[IncidentCardRead.model_validate(c) for c in items],
        total=total,
        page=page,
        size=size,
        pages=ceil(total / size) if size else 0,
    )


# ------------------------------------------------------------------- get

@router.get("/{card_id}", response_model=IncidentCardRead)
async def get_card(
    card_id: int,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(current_user),
):
    c = await IncidentCardService(db).get(card_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card not found")
    return c


# ---------------------------------------------------------------- create

@router.post("", response_model=IncidentCardRead, status_code=status.HTTP_201_CREATED)
async def create_card(
    payload: IncidentCardCreate,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("teacher", "admin")),
):
    card = await IncidentCardService(db).create(payload.model_dump())

    await AuditService(db).log(
        category="cards",
        action=AuditAction.CARD_CREATED,
        user=current,
        entity_type="card",
        entity_id=card.id,
        details={
            "source": card.source,
            "incident_type_code": card.incident_type_code,
        },
    )
    return card


# ---------------------------------------------------------------- update

@router.put("/{card_id}", response_model=IncidentCardRead)
async def update_card(
    card_id: int,
    payload: IncidentCardUpdate,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("teacher", "admin")),
):
    svc = IncidentCardService(db)
    card = await svc.get(card_id)
    if not card:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card not found")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        return card

    updated = await svc.update(card, data)

    await AuditService(db).log(
        category="cards",
        action=AuditAction.CARD_UPDATED,
        user=current,
        entity_type="card",
        entity_id=updated.id,
        details={"changed_fields": sorted(data.keys())},
    )
    return updated


# ---------------------------------------------------------------- delete

@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    card_id: int,
    db: AsyncSession = Depends(get_session),
    current: User = Depends(require_role("admin")),
):
    svc = IncidentCardService(db)
    card = await svc.get(card_id)
    if not card:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card not found")

    await svc.delete(card)

    await AuditService(db).log(
        category="cards",
        action=AuditAction.CARD_DELETED,
        user=current,
        entity_type="card",
        entity_id=card_id,
    )