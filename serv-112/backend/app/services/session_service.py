from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.runtime_action import RuntimeAction
from app.models.runtime_call import RuntimeCall
from app.models.session import TrainingSession


class SessionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_user(self, user_id: int) -> list[TrainingSession]:
        result = await self.db.execute(
            select(TrainingSession)
            .where(TrainingSession.trainee_id == user_id)
            .order_by(TrainingSession.id.desc())
        )
        return list(result.scalars().all())

    async def get_for_user(self, session_id: int, user_id: int) -> TrainingSession | None:
        result = await self.db.execute(
            select(TrainingSession).where(
                TrainingSession.id == session_id,
                TrainingSession.trainee_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, trainee_id: int) -> TrainingSession:
        session = TrainingSession(trainee_id=trainee_id, status="running")
        self.db.add(session)
        await self.db.flush()
        await self.db.refresh(session)
        return session

    async def finish(self, session: TrainingSession) -> tuple[int, dict]:
        rows = (await self.db.execute(
            select(RuntimeCall)
            .where(RuntimeCall.session_id == session.id)
            .order_by(RuntimeCall.created_at)
        )).scalars().all()
        evaluations = [r.evaluation for r in rows if r.evaluation]

        action_rows = (await self.db.execute(
            select(RuntimeAction)
            .where(RuntimeAction.session_id == session.id)
            .order_by(RuntimeAction.created_at, RuntimeAction.step)
        )).scalars().all()

        session.finished_at = datetime.now(timezone.utc)
        session.status = "finished"
        session.actions_log = [
            {
                "callId": a.call_id,
                "step": a.step,
                "actionType": a.action_type,
                "timestampSec": a.timestamp_sec,
                "params": a.params,
            }
            for a in action_rows
        ]
        session.evaluation = {
            "schemaVersion": 1,
            "completedCalls": len(evaluations),
            "calls": evaluations,
        }
        await self.db.flush()
        await self.db.refresh(session)
        return len(evaluations), session.evaluation or {}
