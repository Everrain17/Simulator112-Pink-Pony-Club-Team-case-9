"""finalize runtime calls and sessions

Revision ID: d4e6f7a8b901
Revises: b7e1c4a9d203
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d4e6f7a8b901"
down_revision: Union[str, Sequence[str], None] = "b7e1c4a9d203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Runtime no longer has a Scenario relationship. Legacy Scenario tables
    # remain available for old admin data, but they are not part of runtime.
    # Sessions keep the old nullable scenario_id column for backwards
    # compatibility with existing databases and historical records.
    op.create_index(
        "ix_runtime_calls_session_status",
        "runtime_calls",
        ["session_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_runtime_calls_completed_at",
        "runtime_calls",
        ["completed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_calls_completed_at", table_name="runtime_calls")
    op.drop_index("ix_runtime_calls_session_status", table_name="runtime_calls")
