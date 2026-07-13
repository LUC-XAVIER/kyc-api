"""rename agents.hashed_password -> hashed_pin (credential is a PIN)

Revision ID: d9a1c3f57e42
Revises: b7d2f4a9c810
Create Date: 2026-07-13 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd9a1c3f57e42'
down_revision: str | None = 'b7d2f4a9c810'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        'agents', 'hashed_password', new_column_name='hashed_pin'
    )


def downgrade() -> None:
    op.alter_column(
        'agents', 'hashed_pin', new_column_name='hashed_password'
    )
