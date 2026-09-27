from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class SessionCreate(BaseModel):
    trainee_id: int | None = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    trainee_id: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    score: int


class SessionFinishResponse(BaseModel):
    session_id: int
    status: str
    score: int
    completed_calls: int
    evaluation: dict = Field(default_factory=dict)
