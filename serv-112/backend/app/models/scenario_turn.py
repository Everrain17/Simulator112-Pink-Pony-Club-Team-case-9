from sqlalchemy import String, Text, Boolean, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScenarioTurn(Base):
    __tablename__ = "scenario_turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    turn_index: Mapped[int] = mapped_column(Integer)

    speaker: Mapped[str] = mapped_column(String(16))   # operator / caller
    text: Mapped[str] = mapped_column(Text)
    timestamp_sec: Mapped[float | None] = mapped_column(Float, nullable=True)

    stage: Mapped[str | None] = mapped_column(
        ForeignKey("dialog_stages.code"), nullable=True
    )
    expected_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_key_question: Mapped[bool] = mapped_column(Boolean, default=False)

    emotional_marker: Mapped[str | None] = mapped_column(
        ForeignKey("emotional_states.code"), nullable=True
    )
    contains_address: Mapped[bool] = mapped_column(Boolean, default=False)
    contains_name: Mapped[bool] = mapped_column(Boolean, default=False)