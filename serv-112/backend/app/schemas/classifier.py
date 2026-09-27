from pydantic import BaseModel, ConfigDict, Field


def _camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ServiceRead(BaseModel):
    code: str
    dispatch_code: str
    name: str
    description: str
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="allow")


class IncidentTypeRead(BaseModel):
    code: str
    name: str
    ekp_code: str | None = None
    subgroup: str | None = None
    main_service: str | None = None
    additional_services: list[str] = Field(default_factory=list)
    critical_tags: list[str] = Field(default_factory=list)
    scenario_description: str = ""
    profile_count: int = 0
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="allow")


class DialogStageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    is_required: bool
    order_index: int


class EmotionalStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    description: str


class InterferenceTypeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
