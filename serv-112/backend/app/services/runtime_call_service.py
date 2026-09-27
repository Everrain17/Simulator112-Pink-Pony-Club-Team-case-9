from datetime import datetime, timezone
from typing import Any
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.runtime_action import RuntimeAction
from app.models.runtime_call import RuntimeCall
from app.models.session import TrainingSession
from app.schemas.runtime import (
    OperatorCardSubmission,
    RuntimeActionCreate,
    RuntimeAcceptCall,
    RuntimeInjectCall,
    RuntimeTeacherIntervention,
)
from app.services.simcore_client import SimCoreClient


def _now() -> datetime:
    return datetime.now(timezone.utc)


SERVICE_ALIASES = {
    "101": "MCHS",
    "102": "POLICE",
    "103": "AMBULANCE",
    "104": "GAS",
}


def _norm(values: list[Any] | None) -> set[str]:
    result = set()
    for value in values or []:
        text = str(value).strip().upper()
        if not text:
            continue
        result.add(SERVICE_ALIASES.get(text, text))
    return result


def _flatten_checklist(checklist: dict[str, dict[str, str]] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for template, answers in (checklist or {}).items():
        for field_id, value in (answers or {}).items():
            if value is None:
                continue
            text = str(value).strip()
            if text:
                result[f"{template}::{field_id}"] = text
    return result


FLAG_TO_TAG = {
    "casualties": "CASUALTIES",
}


def _operator_tags(flags: dict[str, Any]) -> set[str]:
    return {
        FLAG_TO_TAG[str(k)]
        for k, value in (flags or {}).items()
        if bool(value) and str(k) in FLAG_TO_TAG
    }


def evaluate_call(card: dict[str, Any], engine: dict[str, Any]) -> dict[str, Any]:
    gt = engine.get("groundTruth") or engine.get("ground_truth") or {}
    classifier = card.get("classifier") or {}
    services = card.get("services") or {}
    flags = card.get("flags") or {}

    expected_type = str(
        gt.get("expectedIncidentType") or gt.get("expected_incident_type") or ""
    )
    actual_type = str(
        classifier.get("selectedType") or classifier.get("selected_type") or ""
    )

    expected_services = _norm(
        gt.get("requiredServices") or gt.get("required_services")
    )
    selected_services = _norm(services.get("selected"))
    missing_services = sorted(expected_services - selected_services)
    extra_services = sorted(selected_services - expected_services)

    critical_tags = {
        str(x).strip().upper()
        for x in (gt.get("criticalTags") or gt.get("critical_tags") or [])
        if str(x).strip()
    }
    optional_tags = {
        str(x).strip().upper()
        for x in (gt.get("optionalTags") or gt.get("optional_tags") or [])
        if str(x).strip()
    }
    operator_tags = _operator_tags(flags)
    missing_critical_tags = sorted(critical_tags - operator_tags)
    unexpected_operator_tags = sorted(operator_tags - critical_tags - optional_tags)

    classification_correct = bool(expected_type) and expected_type == actual_type

    return {
        "schemaVersion": 1,
        "classification": {
            "expected": expected_type,
            "actual": actual_type,
            "correct": classification_correct,
        },
        "services": {
            "required": sorted(expected_services),
            "selected": sorted(selected_services),
            "missing": missing_services,
            "extra": extra_services,
            "allRequiredSelected": not missing_services,
        },
        "flags": {
            "operator": flags,
            "operatorCanonicalTags": sorted(operator_tags),
            "groundTruthCriticalTags": sorted(critical_tags),
            "groundTruthOptionalTags": sorted(optional_tags),
            "missingCriticalTags": missing_critical_tags,
            "unexpectedOperatorTags": unexpected_operator_tags,
        },
        "checklist": {
            "answers": card.get("checklist") or {},
        },
        "serviceReasons": services.get("reasons") or {},
        "engineAnalysis": engine.get("analysis") or {},
        "textAnalysis": engine.get("textAnalysis") or engine.get("text_analysis"),
        "groundTruth": gt,
        "operatorCard": card,
        "operatorCardMatchesGroundTruth": {
            "classification": classification_correct,
            "services": not missing_services,
            "criticalFlags": not missing_critical_tags,
        },
    }


class RuntimeCallService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.simcore = SimCoreClient()

    async def get(self, call_id: str) -> RuntimeCall | None:
        return await self.db.get(RuntimeCall, call_id)

    async def _get_or_create(
        self,
        call_id: str,
        *,
        session_id: int | None = None,
        student_id: str | None = None,
        operator_id: int | None = None,
    ) -> RuntimeCall:
        row = await self.db.get(RuntimeCall, call_id)
        if row is not None:
            if session_id is not None:
                row.session_id = session_id
            if student_id:
                row.student_id = student_id
            if operator_id is not None:
                row.operator_id = operator_id
            return row
        row = RuntimeCall(
            call_id=call_id,
            session_id=session_id,
            student_id=student_id,
            operator_id=operator_id,
            status="open",
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def _ensure_session(self, session_id: int | None) -> None:
        if session_id is None:
            return
        session = await self.db.get(TrainingSession, session_id)
        if session is None:
            raise ValueError(f"TrainingSession {session_id} не найдена")
        if session.status != "running":
            raise ValueError(f"TrainingSession {session_id} уже завершена")

    async def inject(self, payload: RuntimeInjectCall) -> dict:
        await self._ensure_session(payload.session_id)
        data = await self.simcore.inject({
            "incidentTypeCode": payload.incident_type_code,
            "severity": payload.severity,
            "initialPanic": payload.initial_panic,
            "requiredServiceCodes": payload.required_service_codes,
            "criticalTagCodes": payload.critical_tag_codes,
            "optionalTagCodes": payload.optional_tag_codes,
            "ekpCode": payload.ekp_code,
            "ekpName": payload.ekp_name,
            "description": payload.description,
            "address": payload.address,
            "lat": payload.lat,
            "lon": payload.lon,
            "customUtterance": payload.custom_utterance,
            "teacherComment": payload.teacher_comment,
        })
        call_id = str(data.get("callId") or "")
        if not call_id:
            raise ValueError("SimCore не вернул callId")
        row = await self._get_or_create(
            call_id,
            session_id=payload.session_id,
        )
        row.incident_id = data.get("incidentId")
        await self.db.flush()
        return data

    async def accept(
        self,
        call_id: str,
        payload: RuntimeAcceptCall,
        operator_id: int | None = None,
    ) -> dict:
        await self._ensure_session(payload.session_id)
        data = await self.simcore.accept_call({
            "callId": call_id,
            "studentId": payload.student_id,
            "phoneNumber": payload.phone_number,
        })
        row = await self._get_or_create(
            call_id,
            session_id=payload.session_id,
            student_id=payload.student_id,
            operator_id=operator_id,
        )
        row.status = "accepted"
        await self.record_action(RuntimeActionCreate(
            call_id=call_id,
            session_id=payload.session_id,
            student_id=payload.student_id,
            action_type="CALL_ACCEPTED",
            timestamp_sec=0.0,
            params={"phoneNumber": payload.phone_number or ""},
        ), operator_id=operator_id)
        return data

    async def record_action(
        self,
        payload: RuntimeActionCreate,
        operator_id: int | None = None,
    ) -> RuntimeAction:
        row = await self._get_or_create(
            payload.call_id,
            session_id=payload.session_id,
            student_id=payload.student_id,
            operator_id=operator_id,
        )
        next_step = (await self.db.execute(
            select(func.coalesce(func.max(RuntimeAction.step), 0) + 1)
            .where(RuntimeAction.call_id == payload.call_id)
        )).scalar_one()
        action = RuntimeAction(
            call_id=payload.call_id,
            session_id=payload.session_id or row.session_id,
            operator_id=operator_id if operator_id is not None else row.operator_id,
            step=int(next_step),
            action_type=payload.action_type,
            timestamp_sec=payload.timestamp_sec,
            params=payload.params or {},
        )
        self.db.add(action)
        await self.db.flush()
        return action

    async def intervene(self, call_id: str, payload: RuntimeTeacherIntervention) -> dict:
        return await self.simcore.teacher_intervene({
            "callId": call_id,
            "comment": payload.comment,
        })

    async def save_card(
        self,
        payload: OperatorCardSubmission,
        operator_id: int | None = None,
    ) -> RuntimeCall:
        await self._ensure_session(payload.session_id)
        row = await self._get_or_create(
            payload.call_id,
            session_id=payload.session_id,
            student_id=payload.student_id,
            operator_id=operator_id,
        )
        row.operator_card = payload.model_dump(by_alias=True)
        row.card_received_at = _now()
        if row.status in {"open", "accepted"}:
            row.status = "card_received"
        await self.record_action(
            RuntimeActionCreate(
                call_id=payload.call_id,
                session_id=payload.session_id,
                student_id=payload.student_id,
                action_type="CARD_SAVED",
                timestamp_sec=0.0,
                params={
                    "selectedIncidentType": payload.classifier.selected_type,
                    "services": payload.services.selected,
                },
            ),
            operator_id=operator_id,
        )
        await self.db.flush()
        await self.db.refresh(row)
        return row

    async def complete(self, call_id: str) -> RuntimeCall:
        row = await self._get_or_create(call_id)

        if not row.operator_card:
            raise ValueError(
                "Карточка оператора для этого звонка ещё не сохранена"
            )

        if row.result_json is not None:
            return row

        card = row.operator_card

        engine_snapshot = await self.simcore.snapshot(call_id)

        ground_truth = (
            engine_snapshot.get("groundTruth")
            or engine_snapshot.get("ground_truth")
            or {}
        )

        evaluation = evaluate_call(
            card,
            engine_snapshot
        )

        result_json = {
            "schemaVersion": 1,
            "callId": call_id,
            "sessionId": row.session_id,
            "studentId": row.student_id,
            "operatorId": row.operator_id,
            "savedAt": _now().isoformat(),
            "operatorCard": card,
            "engine": engine_snapshot,
            "groundTruth": ground_truth,
            "dialogue": engine_snapshot.get("dialogue"),
            "analysis": engine_snapshot.get("analysis"),
            "violations": (
                (engine_snapshot.get("dialogue") or {})
                .get("violations", [])
            ),
            "evaluation": evaluation,
        }

        row.result_json = result_json
        row.engine_result = engine_snapshot
        row.evaluation = evaluation

        row.incident_id = (
            engine_snapshot.get("incidentId")
            or row.incident_id
        )

        incident = engine_snapshot.get("incident") or {}

        row.incident_id = (
            incident.get("id")
            or incident.get("Id")
            or row.incident_id
        )

        row.engine_received_at = _now()
        row.status = "saved"

        await self.db.flush()
        await self.db.refresh(row)

        return row

    async def finish(self, call_id: str) -> RuntimeCall:
        row = await self._get_or_create(call_id)

        if not row.operator_card:
            await self.simcore.release_call(
                call_id
            )

            row.status = "released"

            await self.record_action(
                RuntimeActionCreate(
                    call_id=call_id,
                    session_id=row.session_id,
                    student_id=row.student_id,
                    action_type="CALL_RELEASED",
                    timestamp_sec=0.0,
                    params={},
                ),
                operator_id=row.operator_id,
            )

            await self.db.flush()
            await self.db.refresh(row)

            return row

        # Забираем последнее состояние разговора ДО закрытия звонка в C#
        final_state = await self.simcore.snapshot(call_id)

        final_evaluation = evaluate_call(
            row.operator_card,
            final_state
        )

        if row.result_json is not None:
            result_json = dict(row.result_json)
        else:
            result_json = {
                "schemaVersion": 1,
                "callId": call_id,
                "sessionId": row.session_id,
                "studentId": row.student_id,
                "operatorId": row.operator_id,
                "savedAt": _now().isoformat(),
                "operatorCard": row.operator_card,
            }

        result_json["dialogue"] = (
            final_state.get("dialogue")
        )

        result_json["analysis"] = (
            final_state.get("analysis")
        )

        result_json["violations"] = (
            (final_state.get("dialogue") or {})
            .get("violations", [])
        )

        result_json["evaluation"] = final_evaluation
        result_json["finalizedAt"] = _now().isoformat()

        row.result_json = result_json

        row.engine_result = final_state
        row.evaluation = final_evaluation
        row.engine_received_at = _now()

        # Только здесь окончательно закрываем звонок
        await self.simcore.complete_call(call_id)

        row.status = "ended"
        row.completed_at = _now()

        await self.db.flush()
        await self.db.refresh(row)

        return row
