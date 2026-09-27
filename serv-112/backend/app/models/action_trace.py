from datetime import datetime

from sqlalchemy import (
    String, Boolean, Integer, Float, ForeignKey, DateTime, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ActionTrace(Base):
    __tablename__ = "action_traces"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id"), index=True
    )
    operator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    is_reference: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    total_time_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    actions: Mapped[list["ActionStep"]] = relationship(
        back_populates="trace",
        cascade="all, delete-orphan",
        order_by="ActionStep.step",
        lazy="selectin",
    )


class ActionStep(Base):
    __tablename__ = "action_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    trace_id: Mapped[int] = mapped_column(
        ForeignKey("action_traces.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[int] = mapped_column(Integer)
    action_type: Mapped[str] = mapped_column(String(64), index=True)
    timestamp_sec: Mapped[float] = mapped_column(Float)
    params: Mapped[dict] = mapped_column(JSONB, default=dict)

    trace: Mapped["ActionTrace"] = relationship(back_populates="actions")