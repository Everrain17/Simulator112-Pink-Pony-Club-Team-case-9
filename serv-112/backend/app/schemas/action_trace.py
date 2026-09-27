from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ActionStepBase(BaseModel):
    """Один шаг траектории."""
    action_type: str = Field(..., min_length=1, max_length=64)
    timestamp_sec: float = Field(..., ge=0)
    params: dict = Field(default_factory=dict)


class ActionStepRead(ActionStepBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    step: int


class ActionTraceBase(BaseModel):
    scenario_id: int
    operator_id: int | None = None
    is_reference: bool = False
    total_time_sec: float | None = Field(None, ge=0)


class ActionTraceCreate(ActionTraceBase):
    """Создание трейса. Шаги передаются вложенным списком."""
    actions: list[ActionStepBase] = Field(..., min_length=1)


class ActionTraceUpdate(BaseModel):
    """Частичное обновление."""
    operator_id: int | None = None
    is_reference: bool | None = None
    total_time_sec: float | None = Field(None, ge=0)
    actions: list[ActionStepBase] | None = None


class ActionTraceRead(ActionTraceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    actions: list[ActionStepRead] = Field(default_factory=list)


class ActionTracePage(BaseModel):
    items: list[ActionTraceRead]
    total: int
    page: int
    size: int
    pages: int