from typing import Any, NotRequired, TypedDict

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.action_trace import ActionStep, ActionTrace


class _StepData(TypedDict):
    """Один шаг траектории в том виде, как его присылает клиент."""
    action_type: str
    timestamp_sec: float
    params: NotRequired[dict[str, Any]]


class ActionTraceService:
    """Операции над траекториями действий."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ----------------------------------------------------------------- list

    async def list_traces(
        self,
        *,
        scenario_id: int | None = None,
        operator_id: int | None = None,
        is_reference: bool | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[ActionTrace], int]:
        conditions = []
        if scenario_id is not None:
            conditions.append(ActionTrace.scenario_id == scenario_id)
        if operator_id is not None:
            conditions.append(ActionTrace.operator_id == operator_id)
        if is_reference is not None:
            conditions.append(ActionTrace.is_reference == is_reference)

        base = select(ActionTrace)
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
                base.order_by(ActionTrace.id.desc()).offset(offset).limit(size)
            )
        ).scalars().all()

        return list(items), total

    # ------------------------------------------------------------------ get

    async def get(self, trace_id: int) -> ActionTrace | None:
        """Загружает трейс вместе с шагами."""
        q = (
            select(ActionTrace)
            .options(selectinload(ActionTrace.actions))
            .where(ActionTrace.id == trace_id)
            .execution_options(populate_existing=True)
        )
        return (await self.db.execute(q)).scalar_one_or_none()

    # -------------------------------------------------------------- helpers

    def _add_steps(
        self,
        trace_id: int,
        actions: list[_StepData],
    ) -> None:
            self.db.add(ActionStep(
                trace_id=trace_id,
                step=idx,
                action_type=step_data["action_type"],
                timestamp_sec=step_data["timestamp_sec"],
                params=step_data.get("params") or {},
            ))

    # --------------------------------------------------------------- create

    async def create(self, data: dict[str, Any]) -> ActionTrace:
        payload = dict(data)
        actions_data: list[_StepData] = payload.pop("actions", [])

        trace = ActionTrace(**payload)
        self.db.add(trace)
        await self.db.flush()   # получим trace.id

        self._add_steps(trace.id, actions_data)
        await self.db.flush()

        await self.db.refresh(trace, ["actions"])

        result = await self.get(trace.id)
        if result is None:
            raise RuntimeError("trace disappeared after create")
        return result

    # --------------------------------------------------------------- update

    async def update(
        self, trace: ActionTrace, data: dict[str, Any],
    ) -> ActionTrace:
        payload = dict(data)
        new_actions = payload.pop("actions", None)

        for key, value in payload.items():
            setattr(trace, key, value)

        if isinstance(new_actions, list):
            await self.db.execute(
                delete(ActionStep).where(ActionStep.trace_id == trace.id)
            )
            self._add_steps(trace.id, new_actions)
            await self.db.flush()
            await self.db.refresh(trace, ["actions"])

        await self.db.flush()

        result = await self.get(trace.id)
        if result is None:
            raise RuntimeError("trace disappeared after update")
        return result

    # --------------------------------------------------------------- delete

    async def delete(self, trace: ActionTrace) -> None:
        """Физическое удаление. Шаги уйдут каскадом."""
        await self.db.delete(trace)
        await self.db.flush()