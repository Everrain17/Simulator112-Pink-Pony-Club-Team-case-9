from pydantic import BaseModel, ConfigDict, Field


class TurnBase(BaseModel):
    speaker: str = Field(..., pattern="^(operator|caller)$")
    text: str = Field(..., min_length=1)
    timestamp_sec: float | None = Field(None, ge=0)
    stage: str | None = None
    expected_action: str | None = None
    is_key_question: bool = False
    emotional_marker: str | None = None
    contains_address: bool = False
    contains_name: bool = False


class TurnCreate(TurnBase):
    """turn_index проставится автоматически в конец."""


class TurnUpdate(BaseModel):
    speaker: str | None = Field(None, pattern="^(operator|caller)$")
    text: str | None = Field(None, min_length=1)
    timestamp_sec: float | None = Field(None, ge=0)
    stage: str | None = None
    expected_action: str | None = None
    is_key_question: bool | None = None
    emotional_marker: str | None = None
    contains_address: bool | None = None
    contains_name: bool | None = None


class TurnRead(TurnBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scenario_id: int
    turn_index: int


class TurnReorder(BaseModel):
    """Новый порядок реплик: список id в нужной последовательности."""
    ids: list[int] = Field(..., min_length=1)