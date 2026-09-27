from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


def _camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ContractModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=_camel,
        populate_by_name=True,
        extra="allow",
    )


class RuntimeStart(ContractModel):
    seed: int | None = None
    profile: int = Field(0, ge=0, le=4)
    call_answer_time_seconds: int = Field(30, ge=1, le=3600)
    sla_time_seconds: int = Field(75, ge=1, le=3600)
    end_call_time_seconds: int = Field(420, ge=1, le=7200)


class CardClassifier(ContractModel):
    selected_type: str = Field(..., min_length=1, max_length=128)
    ekp_code: str | None = None
    ekp_name: str | None = None


class CardServices(ContractModel):
    selected: list[str] = Field(default_factory=list)
    required: list[str] = Field(default_factory=list)
    manual: list[str] = Field(default_factory=list)
    reasons: dict[str, list[str]] = Field(default_factory=dict)


class OperatorCardSubmission(ContractModel):
    schema_version: int = Field(1, ge=1)
    call_id: str = Field(..., min_length=1, max_length=64)
    student_id: str = Field(..., min_length=1, max_length=64)
    session_id: int | None = None
    applicant: dict[str, Any] = Field(default_factory=dict)
    applicant_role: str | None = None
    phones: dict[str, Any] = Field(default_factory=dict)
    address: dict[str, Any] = Field(default_factory=dict)
    description: str = ""
    operator_notes: str = ""
    classifier: CardClassifier
    flags: dict[str, bool] = Field(default_factory=dict)
    checklist: dict[str, dict[str, str]] = Field(default_factory=dict)
    services: CardServices = Field(default_factory=CardServices)
    engine: dict[str, Any] = Field(default_factory=dict)


class RuntimeActionCreate(ContractModel):
    call_id: str = Field(..., min_length=1, max_length=64)
    session_id: int | None = None
    student_id: str | None = None
    action_type: str = Field(..., min_length=1, max_length=64)
    timestamp_sec: float = Field(0.0, ge=0)
    params: dict[str, Any] = Field(default_factory=dict)


class RuntimeInjectCall(ContractModel):
    session_id: int | None = None
    incident_type_code: str = Field(..., min_length=1, max_length=128)
    severity: int = Field(60, ge=0, le=100)
    initial_panic: int = Field(50, ge=0, le=100)
    required_service_codes: list[str] = Field(default_factory=list)
    critical_tag_codes: list[str] = Field(default_factory=list)
    optional_tag_codes: list[str] = Field(default_factory=list)
    ekp_code: str | None = None
    ekp_name: str | None = None
    description: str = ""
    address: str = ""
    lat: float = 0.0
    lon: float = 0.0
    custom_utterance: str | None = None
    teacher_comment: str | None = None


class RuntimeAcceptCall(ContractModel):
    student_id: str = Field(..., min_length=1, max_length=64)
    session_id: int | None = None
    phone_number: str | None = None


class RuntimeTeacherIntervention(ContractModel):
    comment: str = Field(..., min_length=1, max_length=4000)


class RuntimeResultRead(ContractModel):
    call_id: str
    status: str
    card_received: bool
    engine_received: bool
    evaluation: dict[str, Any] | None = None
    completed_at: datetime | None = None


class EngineGroundTruth(ContractModel):
    call_id: str
    incident_id: str
    expected_incident_type: str
    critical_tags: list[str] = Field(default_factory=list)
    optional_tags: list[str] = Field(default_factory=list)
    required_services: list[str] = Field(default_factory=list)
    address: str = ""


class EngineCompletion(ContractModel):
    call_id: str
    incident_id: str
    student_id: str
    ground_truth: EngineGroundTruth
    analysis: dict[str, Any] = Field(default_factory=dict)
    dispatched_services: list[str] = Field(default_factory=list)
    completed_at: str | None = None
    text_analysis: dict[str, Any] | None = None
    selected_incident_type: str
    checklist: dict[str, Any] | None = None
