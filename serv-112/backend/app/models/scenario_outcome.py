from sqlalchemy import String, Boolean, Integer, Float, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScenarioOutcome(Base):
    __tablename__ = "scenario_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("scenarios.id", ondelete="CASCADE"), unique=True
    )

    classification_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    fields_required: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list
    )
    fields_optional: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list
    )
    time_to_classify_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)