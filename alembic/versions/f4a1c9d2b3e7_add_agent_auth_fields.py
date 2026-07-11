"""add agent auth fields (email, password, role)

Revision ID: f4a1c9d2b3e7
Revises: e08620485bc8
Create Date: 2026-07-10 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4a1c9d2b3e7'
down_revision: str | None = 'e08620485bc8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

agent_role = sa.Enum('AGENT', 'MANAGER', 'ADMIN', name='agent_role')


def upgrade() -> None:
    agent_role.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'agents', sa.Column('email', sa.String(255), nullable=True)
    )
    op.add_column(
        'agents',
        sa.Column('hashed_password', sa.String(255), nullable=True),
    )
    op.add_column(
        'agents',
        sa.Column(
            'role', agent_role, nullable=False, server_default='AGENT'
        ),
    )
    op.create_unique_constraint('uq_agents_email', 'agents', ['email'])


def downgrade() -> None:
    op.drop_constraint('uq_agents_email', 'agents', type_='unique')
    op.drop_column('agents', 'role')
    op.drop_column('agents', 'hashed_password')
    op.drop_column('agents', 'email')
    agent_role.drop(op.get_bind(), checkfirst=True)
