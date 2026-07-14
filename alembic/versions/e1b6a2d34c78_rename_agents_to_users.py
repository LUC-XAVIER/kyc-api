"""rename agents table -> users (holds all staff, not only agents)

Revision ID: e1b6a2d34c78
Revises: d9a1c3f57e42
Create Date: 2026-07-13 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e1b6a2d34c78'
down_revision: str | None = 'd9a1c3f57e42'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.rename_table('agents', 'users')


def downgrade() -> None:
    op.rename_table('users', 'agents')
