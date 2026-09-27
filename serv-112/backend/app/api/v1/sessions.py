from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_session
from app.api.deps import current_user, require_role
from app.models.user import User
from app.models.session import TrainingSession
from app.schemas.session import SessionCreate, SessionFinishResponse, SessionRead
from app.services.session_service import SessionService

router = APIRouter()


@router.get("/my", response_model=list[SessionRead])
async def my_sessions(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    return await SessionService(db).list_for_user(user.id)


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    trainee_id = payload.trainee_id or user.id
    if trainee_id != user.id and user.role not in {"teacher", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
    session = await SessionService(db).create(trainee_id)
    await db.commit()
    return session


@router.post("/{session_id}/finish", response_model=SessionFinishResponse)
async def finish_session(
    session_id: int,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(current_user),
):
    session = await db.get(TrainingSession, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "TrainingSession не найдена")
    if session.trainee_id != user.id and user.role not in {"teacher", "admin"}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
    if session.status == "finished":
        completed = len((session.evaluation or {}).get("calls") or [])
        return SessionFinishResponse(
            session_id=session.id,
            status=session.status,
            score=session.score,
            completed_calls=completed,
            evaluation=session.evaluation or {},
        )
    completed_calls, evaluation = await SessionService(db).finish(session)
    await db.commit()
    return SessionFinishResponse(
        session_id=session.id,
        status=session.status,
        score=session.score,
        completed_calls=completed_calls,
        evaluation=evaluation,
    )
