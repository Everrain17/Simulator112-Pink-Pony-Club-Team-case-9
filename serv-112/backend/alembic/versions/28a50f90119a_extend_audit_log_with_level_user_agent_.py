"""extend audit_log with level user_agent request_id duration_ms

Revision ID: 28a50f90119a
Revises: 28286d28b0e5
Create Date: 2026-09-17 16:34:37.426711

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28a50f90119a'
down_revision: Union[str, Sequence[str], None] = '28286d28b0e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- level: NOT NULL с server_default='info' для backfill существующих
    #     строк, затем server_default убираем (модель использует default
    #     на стороне Python).
    op.add_column(
        "audit_log",
        sa.Column("level", sa.String(length=16), nullable=False,
                  server_default="info"),
    )
    op.alter_column("audit_log", "level", server_default=None)

    op.add_column(
        "audit_log",
        sa.Column("user_agent", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "audit_log",
        sa.Column("request_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "audit_log",
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )

    # --- индексы. Имена совпадают с naming_convention из
    #     app/database.py, чтобы модель и БД не расходились.
    op.create_index("ix_audit_log_level",      "audit_log", ["level"])
    op.create_index("ix_audit_log_request_id", "audit_log", ["request_id"])
    op.create_index("ix_audit_log_level_ts",   "audit_log",
                    ["level", "timestamp"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_audit_log_level_ts",   table_name="audit_log")
    op.drop_index("ix_audit_log_request_id", table_name="audit_log")
    op.drop_index("ix_audit_log_level",      table_name="audit_log")

    op.drop_column("audit_log", "duration_ms")
    op.drop_column("audit_log", "request_id")
    op.drop_column("audit_log", "user_agent")
    op.drop_column("audit_log", "level")