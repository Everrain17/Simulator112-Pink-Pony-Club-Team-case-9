from datetime import datetime
from sqlalchemy import String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class IncidentCard(Base):
    """
    Stored card/document. The incident_type_code is a canonical SimCore code,
    not a foreign key to a Python classifier table.
    """
    __tablename__ = "incident_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default="synthetic", index=True)
    raw_text: Mapped[str] = mapped_column(Text)
    incident_type_code: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    ekp_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    subtype: Mapped[str | None] = mapped_column(String(128), nullable=True)
    priority: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fields: Mapped[dict] = mapped_column(JSONB, default=dict)
    validation: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
