from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class CardField(BaseModel):
    value: str | None = None
    required: bool = False


class IncidentCardBase(BaseModel):
    source: str = Field("synthetic", pattern="^(synthetic|real|import)$")
    raw_text: str = Field(..., min_length=1)
    incident_type_code: str | None = Field(None, max_length=128)
    ekp_code: str | None = Field(None, max_length=64)
    subtype: str | None = Field(None, max_length=128)
    priority: str | None = Field(None, pattern="^(low|medium|high)$")
    fields: dict[str, CardField] = Field(default_factory=dict)


class IncidentCardCreate(IncidentCardBase):
    pass


class IncidentCardUpdate(BaseModel):
    source: str | None = Field(None, pattern="^(synthetic|real|import)$")
    raw_text: str | None = Field(None, min_length=1)
    incident_type_code: str | None = Field(None, max_length=128)
    ekp_code: str | None = Field(None, max_length=64)
    subtype: str | None = Field(None, max_length=128)
    priority: str | None = Field(None, pattern="^(low|medium|high)$")
    fields: dict[str, CardField] | None = None
    classification_confidence: float | None = Field(None, ge=0, le=1)


class IncidentCardRead(IncidentCardBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    validation: dict
    created_at: datetime


class IncidentCardPage(BaseModel):
    items: list[IncidentCardRead]
    total: int
    page: int
    size: int
    pages: int
