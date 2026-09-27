from datetime import datetime, timezone
from time import time_ns

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.database import get_session
from app.models.runtime_call import RuntimeCall
from app.models.session import TrainingSession
from app.models.user import User
from app.schemas.runtime import (
    OperatorCardSubmission,
    RuntimeActionCreate,
    RuntimeAcceptCall,
    RuntimeInjectCall,
    RuntimeResultRead,
    RuntimeStart,
    RuntimeTeacherIntervention,
)
from app.services.runtime_call_service import RuntimeCallService
from app.services.simcore_client import SimCoreClient, SimCoreError

router = APIRouter()


def _public_evaluation(evaluation: dict | None) -> dict | None:
    if not evaluation:
        return None
    classification = evaluation.get("classification") or {}
    services = evaluation.get("services") or {}
    flags = evaluation.get("flags") or {}
    return {
        "schemaVersion": evaluation.get("schemaVersion", 1),
        "classification": {"correct": bool(classification.get("correct"))},
        "services": {
            "allRequiredSelected": bool(services.get("allRequiredSelected")),
            "missingCount": len(services.get("missing") or []),
            "extraCount": len(services.get("extra") or []),
        },
        "flags": {
            "criticalFlagsCorrect": not bool(flags.get("missingCriticalTags")),
        },
    }


def _serialize_public(row) -> dict:
    return {
        "callId": row.call_id,
        "status": row.status,
        "cardReceived": row.operator_card is not None,
        "engineReceived": row.engine_result is not None,
        "evaluation": _public_evaluation(row.evaluation),
        "completedAt": row.completed_at,
    }

def _serialize_evaluation(evaluation: dict | None) -> dict | None:
    if not evaluation:
        return None

    classification = evaluation.get("classification") or {}
    services = evaluation.get("services") or {}
    flags = evaluation.get("flags") or {}
    
    return {
        "schemaVersion": evaluation.get("schemaVersion", 1),

        "classification": {
            "actual": classification.get("actual"),
            "expected": classification.get("expected"),
            "correct": bool(classification.get("correct")),
        },

        "services": {
            "selected": services.get("selected", []),
            "required": services.get("required", []),
            "missing": services.get("missing", []),
            "extra": services.get("extra", []),
            "allRequiredSelected": bool(
                services.get("allRequiredSelected")
            ),
        },

        "flags": {
            "selected": flags.get("selected", []),
            "required": flags.get("required", []),
            "missingCriticalTags": flags.get(
                "missingCriticalTags",
                []
            ),
            "correct": not bool(
                flags.get("missingCriticalTags")
            ),
        },

        "operatorCardMatchesGroundTruth": (
            evaluation.get("operatorCardMatchesGroundTruth")
        ),
    }
    
def _serialize_private(row) -> dict:
    result = row.result_json or {}

    return {
        "callId": row.call_id,
        "status": row.status,
        "sessionId": row.session_id,
        "studentId": row.student_id,
        "operatorId": row.operator_id,
        "incidentId": row.incident_id,

        "cardReceived": row.operator_card is not None,
        "engineReceived": row.engine_result is not None,

        "operatorCard": result.get(
            "operatorCard",
            row.operator_card
        ),

        "groundTruth": result.get("groundTruth"),

        "dialogue": result.get("dialogue"),

        "analysis": result.get("analysis"),

        "violations": result.get("violations"),

        "evaluation": _serialize_evaluation(
            result.get("evaluation", row.evaluation)
        ),

        "completedAt": row.completed_at,
    }


async def _start_simcore(payload: RuntimeStart) -> dict:
    seed = payload.seed if payload.seed is not None else time_ns() % 2147483647
    try:
        return await SimCoreClient().start({
            "seed": seed,
            "profile": payload.profile,
            "callAnswerTimeSeconds": payload.call_answer_time_seconds,
            "slaTimeSeconds": payload.sla_time_seconds,
            "endCallTimeSeconds": payload.end_call_time_seconds,
            "criteria": None,
        })
    except SimCoreError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.get("/classifier")
async def runtime_classifier():
    try:
        return await SimCoreClient().classifier()
    except SimCoreError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.get("/state")
async def runtime_state():
    try:
        data = await SimCoreClient().state()
    except SimCoreError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc

    active_calls_raw = data.get("activeCalls", []) or []
    active_ids = {
        str(c.get("incidentId") or c.get("IncidentId") or "")
        for c in active_calls_raw
    }
    public_incidents = []
    for incident in data.get("allIncidents", []) or []:
        incident_id = str(incident.get("id") or incident.get("Id") or "")
        is_active = incident_id in active_ids
        item = {
            "id": incident_id,
            "state": incident.get("state") or incident.get("State"),
            "address": "" if is_active else (incident.get("address") or incident.get("Address") or ""),
            "description": "" if is_active else (incident.get("description") or incident.get("Description") or ""),
        }
        if not is_active:
            item["type"] = incident.get("type") or incident.get("Type")
            item["severity"] = incident.get("severity") or incident.get("Severity")
        public_incidents.append(item)

    active_calls = []
    for call in active_calls_raw:
        caller_raw = call.get("caller") or call.get("Caller") or {}
        caller = {
            "id": caller_raw.get("id") or caller_raw.get("Id"),
            "currentEmotion": caller_raw.get("currentEmotion") or caller_raw.get("CurrentEmotion"),
            "panicLevel": caller_raw.get("panicLevel") if caller_raw.get("panicLevel") is not None else caller_raw.get("PanicLevel"),
            "cooperativeness": caller_raw.get("cooperativeness") if caller_raw.get("cooperativeness") is not None else caller_raw.get("Cooperativeness"),
            "lastUtterance": caller_raw.get("lastUtterance") or caller_raw.get("LastUtterance") or "",
            "hasHungUp": caller_raw.get("hasHungUp") if caller_raw.get("hasHungUp") is not None else caller_raw.get("HasHungUp"),
            "phoneNumber": caller_raw.get("phoneNumber") or caller_raw.get("PhoneNumber") or "",
        }
        active_calls.append({
            "id": call.get("id") or call.get("Id"),
            "incidentId": call.get("incidentId") or call.get("IncidentId"),
            "studentId": call.get("studentId") or call.get("StudentId") or "Свободен",
            "timeRemainingSeconds": call.get("timeRemainingSeconds") or call.get("TimeRemainingSeconds"),
            "silenceDurationSeconds": call.get("silenceDurationSeconds") or call.get("SilenceDurationSeconds"),
            "caller": caller,
            "cardState": call.get("cardState") or call.get("CardState"),
            "timeToConfirmSeconds": call.get("timeToConfirmSeconds") or call.get("TimeToConfirmSeconds"),
        })

    return {
        "schemaVersion": 1,
        "isRunning": bool(data.get("isRunning")),
        "elapsedSeconds": data.get("elapsedSeconds", 0),
        "elapsedTicks": data.get("elapsedTicks", 0),
        "activeCalls": active_calls,
        "allIncidents": public_incidents,
    }


@router.get("/available-calls")
async def available_calls():
    try:
        data = await SimCoreClient().available_calls()
    except SimCoreError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return {
        "availableCalls": [
            {
                "callId": call.get("callId") or call.get("id"),
                "callerPhone": call.get("phoneNumber") or call.get("callerPhone") or "",
            }
            for call in (data.get("availableCalls", []) or [])
        ]
    }


@router.post("/start")
async def start_runtime(
    payload: RuntimeStart,
    _: User = Depends(require_role("teacher", "admin")),
):
    return await _start_simcore(payload)


@router.post("/sessions/{session_id}/start")
async def start_runtime_session(
    session_id: int,
    payload: RuntimeStart | None = None,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_role("teacher", "admin")),
):
    session = await db.get(TrainingSession, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "TrainingSession не найдена")
    if session.status == "finished":
        raise HTTPException(status.HTTP_409_CONFLICT, "TrainingSession уже завершена")
    result = await _start_simcore(payload or RuntimeStart())
    session.status = "running"
    session.started_at = datetime.now(timezone.utc)
    await db.commit()
    return {**result, "sessionId": session_id}


@router.post("/stop")
async def stop_runtime(_: User = Depends(require_role("teacher", "admin"))):
    try:
        return await SimCoreClient().stop()
    except SimCoreError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.post("/inject")
async def inject_call_direct(
    payload: RuntimeInjectCall,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_role("teacher", "admin")),
):
    try:
        result = await RuntimeCallService(db).inject(payload)
        await db.commit()
        return result
    except SimCoreError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/sessions/{session_id}/inject")
async def inject_call_session(
    session_id: int,
    payload: RuntimeInjectCall,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_role("teacher", "admin")),
):
    payload.session_id = session_id
    try:
        result = await RuntimeCallService(db).inject(payload)
        await db.commit()
        return result
    except SimCoreError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/calls/{call_id}/accept")
async def accept_call(
    call_id: str,
    payload: RuntimeAcceptCall,
    db: AsyncSession = Depends(get_session),
):
    try:
        result = await RuntimeCallService(db).accept(call_id, payload)
        await db.commit()
        return result
    except SimCoreError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc


@router.post("/calls/{call_id}/action")
async def record_action(
    call_id: str,
    payload: RuntimeActionCreate,
    db: AsyncSession = Depends(get_session),
):
    if payload.call_id != call_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CallId в URL и payload не совпадает")
    action = await RuntimeCallService(db).record_action(payload)
    await db.commit()
    return {"id": action.id, "step": action.step, "actionType": action.action_type}


@router.post("/calls/{call_id}/intervene")
async def intervene(
    call_id: str,
    payload: RuntimeTeacherIntervention,
    _: User = Depends(require_role("teacher", "admin")),
):
    if not call_id.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CallId не указан")
    try:
        return await SimCoreClient().teacher_intervene({
            "callId": call_id,
            "comment": payload.comment,
        })
    except SimCoreError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.post("/calls/{call_id}/card", response_model=RuntimeResultRead)
async def receive_card(
    call_id: str,
    payload: OperatorCardSubmission,
    db: AsyncSession = Depends(get_session),
):
    if payload.call_id != call_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "CallId в URL и payload не совпадает")
    row = await RuntimeCallService(db).save_card(payload)
    await db.commit()
    return _serialize_public(row)


@router.post("/calls/{call_id}/complete", response_model=RuntimeResultRead)
async def complete_call(
    call_id: str,
    db: AsyncSession = Depends(get_session),
):
    try:
        row = await RuntimeCallService(db).complete(call_id)
        await db.commit()
        return _serialize_public(row)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except SimCoreError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

@router.post("/calls/{call_id}/finish", response_model=RuntimeResultRead)
async def finish_call(
    call_id: str,
    db: AsyncSession = Depends(get_session),
):
    try:
        row = await RuntimeCallService(db).finish(call_id)
        await db.commit()
        return _serialize_public(row)

    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            str(exc)
        ) from exc

    except SimCoreError as exc:
        await db.rollback()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            str(exc)
        ) from exc
        
@router.get("/calls/{call_id}/result", response_model=RuntimeResultRead)
async def get_call_result(
    call_id: str,
    db: AsyncSession = Depends(get_session),
):
    row = await RuntimeCallService(db).get(call_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Runtime call not found")
    return _serialize_public(row)


@router.get("/teacher/calls/{call_id}/result")
async def get_teacher_call_result(
    call_id: str,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_role("teacher", "admin")),
):
    row = await RuntimeCallService(db).get(call_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Runtime call not found")
    return _serialize_private(row)
    
@router.get("/teacher/calls")
async def list_teacher_calls(
    student_id: str | None = Query(None, alias="studentId"),
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_role("teacher", "admin")),
):
    query = (
        select(RuntimeCall)
        .order_by(RuntimeCall.created_at.desc())
    )

    if student_id:
        query = query.where(
            RuntimeCall.student_id == student_id
        )

    result = await db.execute(query)
    rows = result.scalars().all()

    return {
        "items": [
            _serialize_private(row)
            for row in rows
        ]
    }

@router.get("/calls/saved")
async def list_saved_calls(
    student_id: str | None = Query(None, alias="studentId"),
    db: AsyncSession = Depends(get_session),
):
    query = select(RuntimeCall).order_by(RuntimeCall.created_at.desc())
    if student_id:
        query = query.where(RuntimeCall.student_id == student_id)
    result = await db.execute(query)
    rows = result.scalars().all()
    return {
        "items": [
            {
                **_serialize_public(row),
                "operatorCard": row.operator_card,
            }
            for row in rows
        ]
    }
