from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident_card import IncidentCard


def _normalize_fields(fields: dict | None) -> dict:
    """Приводит fields к каноническому виду."""
    normalized: dict[str, dict] = {}
    for name, spec in (fields or {}).items():
        if not isinstance(spec, dict):
            continue
        value = spec.get("value")
        if isinstance(value, str):
            value = value.strip() or None
        required = bool(spec.get("required", False))
        normalized[name] = {
            "value": value,
            "required": required,
            "filled": value is not None,
        }
    return normalized


def _build_validation(fields: dict | None, confidence: float | None) -> dict:
    """Пересчитывает validation на основе fields."""
    fields = fields or {}
    missing = [
        name for name, spec in fields.items()
        if spec.get("required") and not spec.get("filled")
    ]
    return {
        "all_required_filled": len(missing) == 0,
        "missing_fields": missing,
        "classification_confidence": confidence,
    }


class IncidentCardService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ list

    async def list(
        self,
        *,
        search: str | None = None,
        incident_type_code: str | None = None,
        source: str | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[IncidentCard], int]:
        conditions = []
        if incident_type_code:
            conditions.append(IncidentCard.incident_type_code == incident_type_code)
        if source:
            conditions.append(IncidentCard.source == source)
        if search:
            like = f"%{search.strip()}%"
            conditions.append(IncidentCard.raw_text.ilike(like))

        base = select(IncidentCard)
        if conditions:
            base = base.where(*conditions)

        total = (
            await self.db.execute(
                select(func.count()).select_from(base.subquery())
            )
        ).scalar_one()

        offset = (page - 1) * size
        items = (
            await self.db.execute(
                base.order_by(IncidentCard.id.desc()).offset(offset).limit(size)
            )
        ).scalars().all()

        return list(items), total

    # ------------------------------------------------------------------- get

    async def get(self, card_id: int) -> IncidentCard | None:
        return await self.db.get(IncidentCard, card_id)

    # ---------------------------------------------------------------- create

    async def create(self, data: dict) -> IncidentCard:
        payload = dict(data)
        fields = _normalize_fields(payload.pop("fields", {}))
        validation = _build_validation(fields, confidence=None)

        card = IncidentCard(
            **payload,
            fields=fields,
            validation=validation,
        )
        self.db.add(card)
        await self.db.flush()
        await self.db.refresh(card)
        return card

    # ---------------------------------------------------------------- update

    async def update(self, card: IncidentCard, data: dict) -> IncidentCard:
        payload = dict(data)
        new_fields = payload.pop("fields", None)
        new_confidence = payload.pop("classification_confidence", None)

        for key, value in payload.items():
            setattr(card, key, value)

        if new_fields is not None:
            fields = _normalize_fields(new_fields)
        else:
            fields = card.fields or {}

        if new_confidence is not None:
            confidence = new_confidence
        else:
            confidence = (card.validation or {}).get("classification_confidence")

        card.fields = fields
        card.validation = _build_validation(fields, confidence)

        await self.db.flush()
        await self.db.refresh(card)
        return card

    # ---------------------------------------------------------------- delete

    async def delete(self, card: IncidentCard) -> None:
        """Физическое удаление. Карточки — самостоятельные записи."""
        await self.db.delete(card)
        await self.db.flush()