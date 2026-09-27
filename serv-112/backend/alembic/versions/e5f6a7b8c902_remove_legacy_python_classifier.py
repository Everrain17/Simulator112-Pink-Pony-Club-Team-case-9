"""remove legacy Python classifier tables

Revision ID: e5f6a7b8c902
Revises: d4e6f7a8b901
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "e5f6a7b8c902"
down_revision: Union[str, Sequence[str], None] = "d4e6f7a8b901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # These tables were the duplicated Python-owned incident/service taxonomy.
    # All application references were removed in earlier migrations.
    op.drop_index("ix_incident_types_service_code", table_name="incident_types")
    op.drop_index("ix_incident_types_parent_code", table_name="incident_types")
    op.drop_index("ix_incident_types_name", table_name="incident_types")
    op.drop_index("ix_incident_types_is_active", table_name="incident_types")
    op.drop_table("incident_types")
    op.drop_table("services")


def downgrade() -> None:
    # Recreate only the legacy storage shape. Runtime application code still
    # does not reference these tables after downgrade.
    op.create_table(
        "services",
        sa.Column("code", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_services"),
    )
    op.create_table(
        "incident_types",
        sa.Column("code", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("service_code", sa.String(length=8), nullable=False),
        sa.Column("parent_code", sa.String(length=16), nullable=True),
        sa.Column("priority", sa.String(length=16), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_code"],
            ["incident_types.code"],
            name="fk_incident_types_parent_code_incident_types",
        ),
        sa.ForeignKeyConstraint(
            ["service_code"],
            ["services.code"],
            name="fk_incident_types_service_code_services",
        ),
        sa.PrimaryKeyConstraint("code", name="pk_incident_types"),
    )
    op.create_index("ix_incident_types_is_active", "incident_types", ["is_active"])
    op.create_index("ix_incident_types_name", "incident_types", ["name"])
    op.create_index("ix_incident_types_parent_code", "incident_types", ["parent_code"])
    op.create_index("ix_incident_types_service_code", "incident_types", ["service_code"])
