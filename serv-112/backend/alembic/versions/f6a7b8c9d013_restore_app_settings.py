from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f6a7b8c9d013"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c902"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "app_settings" not in inspector.get_table_names():
        op.create_table(
            "app_settings",
            sa.Column("key", sa.String(length=64), nullable=False),
            sa.Column(
                "value",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("key", name=op.f("pk_app_settings")),
        )

        op.alter_column(
            "app_settings",
            "value",
            server_default=None,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "app_settings" in inspector.get_table_names():
        op.drop_table("app_settings")
        op.drop_table("app_settings")