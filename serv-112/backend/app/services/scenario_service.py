from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scenario import Scenario


class ScenarioService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ list

    async def list(
        self,
        *,
        search: str | None = None,
        difficulty: int | None = None,
        is_active: bool | None = None,
        author_id: int | None = None,
        page: int = 1,
        size: int = 50,
    ) -> tuple[list[Scenario], int]:
        """Возвращает (items, total). Пагинация по page/size."""
        conditions = []

        if is_active is not None:
            conditions.append(Scenario.is_active == is_active)
        if difficulty is not None:
            conditions.append(Scenario.difficulty == difficulty)
        if author_id is not None:
            conditions.append(Scenario.author_id == author_id)
        if search:
            like = f"%{search.strip()}%"
            conditions.append(
                or_(Scenario.title.ilike(like), Scenario.description.ilike(like))
            )

        base = select(Scenario)
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
                base.order_by(Scenario.id.desc()).offset(offset).limit(size)
            )
        ).scalars().all()

        return list(items), total

    # ------------------------------------------------------------------- get

    async def get(self, scenario_id: int) -> Scenario | None:
        return await self.db.get(Scenario, scenario_id)

    # ---------------------------------------------------------------- create

    async def create(self, data: dict, author_id: int | None) -> Scenario:
        s = Scenario(**dict(data), author_id=author_id)
        self.db.add(s)
        await self.db.flush()
        await self.db.refresh(s)
        return s

    # ---------------------------------------------------------------- update

    async def update(self, scenario: Scenario, data: dict) -> Scenario:
        if not data:
            return scenario
        for key, value in data.items():
            setattr(scenario, key, value)
        await self.db.flush()
        await self.db.refresh(scenario)
        return scenario

    # ---------------------------------------------------------------- delete

    async def deactivate(self, scenario: Scenario) -> None:
        scenario.is_active = False
        await self.db.flush()