"""detach runtime from scenarios and persist runtime actions

Revision ID: b7e1c4a9d203
Revises: 8c9d2e1f4a71
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b7e1c4a9d203"
down_revision: Union[str, Sequence[str], None] = "8c9d2e1f4a71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_runtime_calls_scenario_id", table_name="runtime_calls")
    op.drop_constraint("fk_runtime_calls_scenario_id_scenarios", "runtime_calls", type_="foreignkey")
    op.drop_column("runtime_calls", "scenario_id")
    op.add_column("runtime_calls", sa.Column("incident_id", sa.String(length=64), nullable=True))
    op.create_index("ix_runtime_calls_incident_id", "runtime_calls", ["incident_id"], unique=False)

    op.alter_column("sessions", "scenario_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("sessions", sa.Column("status", sa.String(length=16), server_default="running", nullable=False))
    op.create_index("ix_sessions_status", "sessions", ["status"], unique=False)

    op.create_table(
        "runtime_actions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("call_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column("step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("timestamp_sec", sa.Float(), nullable=False, server_default="0"),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["runtime_calls.call_id"], name="fk_runtime_actions_call_id_runtime_calls", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], name="fk_runtime_actions_session_id_sessions"),
        sa.ForeignKeyConstraint(["operator_id"], ["users.id"], name="fk_runtime_actions_operator_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_runtime_actions"),
    )
    op.create_index("ix_runtime_actions_call_id", "runtime_actions", ["call_id"], unique=False)
    op.create_index("ix_runtime_actions_session_id", "runtime_actions", ["session_id"], unique=False)
    op.create_index("ix_runtime_actions_operator_id", "runtime_actions", ["operator_id"], unique=False)
    op.create_index("ix_runtime_actions_action_type", "runtime_actions", ["action_type"], unique=False)
    op.create_index("ix_runtime_actions_created_at", "runtime_actions", ["created_at"], unique=False)
    op.create_index("ix_runtime_actions_call_step", "runtime_actions", ["call_id", "step"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_runtime_actions_call_step", table_name="runtime_actions")
    op.drop_index("ix_runtime_actions_created_at", table_name="runtime_actions")
    op.drop_index("ix_runtime_actions_action_type", table_name="runtime_actions")
    op.drop_index("ix_runtime_actions_operator_id", table_name="runtime_actions")
    op.drop_index("ix_runtime_actions_session_id", table_name="runtime_actions")
    op.drop_index("ix_runtime_actions_call_id", table_name="runtime_actions")
    op.drop_table("runtime_actions")
    op.drop_index("ix_sessions_status", table_name="sessions")
    op.drop_column("sessions", "status")
    op.alter_column("sessions", "scenario_id", existing_type=sa.Integer(), nullable=False)
    op.drop_index("ix_runtime_calls_incident_id", table_name="runtime_calls")
    op.drop_column("runtime_calls", "incident_id")
    op.add_column("runtime_calls", sa.Column("scenario_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_runtime_calls_scenario_id_scenarios", "runtime_calls", "scenarios", ["scenario_id"], ["id"])
    op.create_index("ix_runtime_calls_scenario_id", "runtime_calls", ["scenario_id"], unique=False)
