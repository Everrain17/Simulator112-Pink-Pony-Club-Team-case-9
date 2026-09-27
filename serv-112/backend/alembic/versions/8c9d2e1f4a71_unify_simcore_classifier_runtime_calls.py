"""make SimCore the classifier owner and add runtime call persistence

Revision ID: 8c9d2e1f4a71
Revises: 550367b4bdca
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "8c9d2e1f4a71"
down_revision: Union[str, Sequence[str], None] = "550367b4bdca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Stop Python IncidentType/Service tables from being referentially
    # authoritative.  The legacy tables remain in the DB for now; Python
    # application code no longer imports or uses them.  Physical deletion is
    # intentionally postponed until old data is archived/migrated.
    op.drop_constraint(
        "fk_scenarios_incident_type_code_incident_types",
        "scenarios",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_incident_cards_incident_type_code_incident_types",
        "incident_cards",
        type_="foreignkey",
    )

    op.alter_column(
        "scenarios",
        "incident_type_code",
        existing_type=sa.String(length=16),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
    op.add_column(
        "scenarios",
        sa.Column("ekp_code", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_scenarios_ekp_code",
        "scenarios",
        ["ekp_code"],
        unique=False,
    )

    op.alter_column(
        "incident_cards",
        "incident_type_code",
        existing_type=sa.String(length=16),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
    op.add_column(
        "incident_cards",
        sa.Column("ekp_code", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_incident_cards_ekp_code",
        "incident_cards",
        ["ekp_code"],
        unique=False,
    )

    op.create_table(
        "runtime_calls",
        sa.Column("call_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("scenario_id", sa.Integer(), nullable=True),
        sa.Column("operator_id", sa.Integer(), nullable=True),
        sa.Column("student_id", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "operator_card",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "engine_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "evaluation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("card_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("engine_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["operator_id"],
            ["users.id"],
            name="fk_runtime_calls_operator_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenarios.id"],
            name="fk_runtime_calls_scenario_id_scenarios",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_runtime_calls_session_id_sessions",
        ),
        sa.PrimaryKeyConstraint("call_id", name="pk_runtime_calls"),
    )
    op.create_index(
        "ix_runtime_calls_status",
        "runtime_calls",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_runtime_calls_session_id",
        "runtime_calls",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_runtime_calls_scenario_id",
        "runtime_calls",
        ["scenario_id"],
        unique=False,
    )
    op.create_index(
        "ix_runtime_calls_operator_id",
        "runtime_calls",
        ["operator_id"],
        unique=False,
    )
    op.create_index(
        "ix_runtime_calls_student_id",
        "runtime_calls",
        ["student_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_runtime_calls_student_id", table_name="runtime_calls")
    op.drop_index("ix_runtime_calls_operator_id", table_name="runtime_calls")
    op.drop_index("ix_runtime_calls_scenario_id", table_name="runtime_calls")
    op.drop_index("ix_runtime_calls_session_id", table_name="runtime_calls")
    op.drop_index("ix_runtime_calls_status", table_name="runtime_calls")
    op.drop_table("runtime_calls")

    op.drop_index("ix_incident_cards_ekp_code", table_name="incident_cards")
    op.drop_column("incident_cards", "ekp_code")
    op.alter_column(
        "incident_cards",
        "incident_type_code",
        existing_type=sa.String(length=64),
        type_=sa.String(length=16),
        existing_nullable=True,
    )
    op.create_foreign_key(
        "fk_incident_cards_incident_type_code_incident_types",
        "incident_cards",
        "incident_types",
        ["incident_type_code"],
        ["code"],
    )

    op.drop_index("ix_scenarios_ekp_code", table_name="scenarios")
    op.drop_column("scenarios", "ekp_code")
    op.alter_column(
        "scenarios",
        "incident_type_code",
        existing_type=sa.String(length=64),
        type_=sa.String(length=16),
        existing_nullable=True,
    )
    op.create_foreign_key(
        "fk_scenarios_incident_type_code_incident_types",
        "scenarios",
        "incident_types",
        ["incident_type_code"],
        ["code"],
    )
