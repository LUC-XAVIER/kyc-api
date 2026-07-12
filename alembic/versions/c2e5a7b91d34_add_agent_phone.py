"""add agent phone (agents log in by phone)

Revision ID: c2e5a7b91d34
Revises: f4a1c9d2b3e7
Create Date: 2026-07-12 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c2e5a7b91d34'
down_revision: str | None = 'f4a1c9d2b3e7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'agents', sa.Column('phone', sa.String(32), nullable=True)
    )
    op.create_unique_constraint('uq_agents_phone', 'agents', ['phone'])


def downgrade() -> None:
    op.drop_constraint('uq_agents_phone', 'agents', type_='unique')
    op.drop_column('agents', 'phone')
