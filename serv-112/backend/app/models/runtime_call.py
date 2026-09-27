from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class RuntimeCall(Base):
    __tablename__ = "runtime_calls"

    call_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[int | None] = mapped_column(
        ForeignKey("sessions.id"), nullable=True, index=True
    )
    operator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    student_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    incident_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    operator_card: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    engine_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    evaluation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    card_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    engine_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
