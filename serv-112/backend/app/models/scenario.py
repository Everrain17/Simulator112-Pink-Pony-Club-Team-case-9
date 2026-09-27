from datetime import datetime
from sqlalchemy import String, Integer, Text, Boolean, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Scenario(Base):
    """
    Legacy teacher-side template storage.

    Runtime calls are NOT created from this table. A live call is created by
    SimCore teacher injection. The table remains only for old administrative
    data and future optional reusable presets.
    """
    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(Text, default="")
    incident_type_code: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    ekp_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    caller_profile: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
