from typing import Sequence, Union
from alembic import op

revision: str = "550367b4bdca"
down_revision: Union[str, Sequence[str], None] = "692982b70269"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Historical duplicate of 692982b70269. Kept as an explicit no-op so the
    # existing Alembic revision chain remains linear without recreating a table.
    pass


def downgrade() -> None:
    pass
