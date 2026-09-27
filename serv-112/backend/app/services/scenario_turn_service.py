from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario_turn import ScenarioTurn

_TURN_LOCK_NS = 112

class ScenarioTurnService:
    """Операции над репликами одного сценария."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _lock_scenario(self, scenario_id: int) -> None:
        await self.db.execute(
            text("SELECT pg_advisory_xact_lock(:ns, :key)"),
            {"ns": _TURN_LOCK_NS, "key": scenario_id},
        )

    # ------------------------------------------------------------------ list

    async def list_for_scenario(self, scenario_id: int) -> list[ScenarioTurn]:
        q = (
            select(ScenarioTurn)
            .where(ScenarioTurn.scenario_id == scenario_id)
            .order_by(ScenarioTurn.turn_index)
        )
        return list((await self.db.execute(q)).scalars().all())

    # ------------------------------------------------------------------- get

    async def get(self, scenario_id: int, turn_id: int) -> ScenarioTurn | None:
        q = select(ScenarioTurn).where(
            ScenarioTurn.id == turn_id,
            ScenarioTurn.scenario_id == scenario_id,
        )
        return (await self.db.execute(q)).scalar_one_or_none()

    # ---------------------------------------------------------------- create

    async def create(self, scenario_id: int, data: dict) -> ScenarioTurn:
        await self._lock_scenario(scenario_id)

        max_idx = (
            await self.db.execute(
                select(ScenarioTurn.turn_index)
                .where(ScenarioTurn.scenario_id == scenario_id)
                .order_by(ScenarioTurn.turn_index.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        next_idx = (max_idx or 0) + 1
        turn = ScenarioTurn(
            scenario_id=scenario_id, turn_index=next_idx, **dict(data)
        )
        self.db.add(turn)
        await self.db.flush()
        await self.db.refresh(turn)
        return turn

    # ---------------------------------------------------------------- update

    async def update(self, turn: ScenarioTurn, data: dict) -> ScenarioTurn:
        if not data:
            return turn
        for key, value in data.items():
            setattr(turn, key, value)
        await self.db.flush()
        await self.db.refresh(turn)
        return turn

    # ---------------------------------------------------------------- delete

    async def delete(self, turn: ScenarioTurn) -> None:
        """Удаляет реплику и сжимает turn_index у оставшихся."""
        scenario_id = turn.scenario_id
        removed_idx = turn.turn_index

        await self._lock_scenario(scenario_id)

        await self.db.delete(turn)
        await self.db.flush()

        await self.db.execute(
            update(ScenarioTurn)
            .where(
                ScenarioTurn.scenario_id == scenario_id,
                ScenarioTurn.turn_index > removed_idx,
            )
            .values(turn_index=ScenarioTurn.turn_index - 1)
        )
        await self.db.flush()

    # --------------------------------------------------------------- reorder

    async def reorder(
        self, scenario_id: int, ordered_ids: list[int]
    ) -> list[ScenarioTurn]:
        await self._lock_scenario(scenario_id)

        existing = await self.list_for_scenario(scenario_id)
        existing_ids = {t.id for t in existing}
        requested_ids = list(ordered_ids)

        if len(requested_ids) != len(set(requested_ids)):
            raise ValueError("ordered_ids contains duplicates")
        if set(requested_ids) != existing_ids:
            raise ValueError(
                "ordered_ids must contain exactly all turn ids of the scenario"
            )

        by_id = {t.id: t for t in existing}
        for new_idx, turn_id in enumerate(requested_ids, start=1):
            by_id[turn_id].turn_index = new_idx

        await self.db.flush()
        return [by_id[i] for i in requested_ids]