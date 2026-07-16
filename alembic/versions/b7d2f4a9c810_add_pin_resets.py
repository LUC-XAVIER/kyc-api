"""add pin_resets (manager forgot-PIN)

Revision ID: b7d2f4a9c810
Revises: a3f8c1e64b52
Create Date: 2026-07-13 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7d2f4a9c810'
down_revision: str | None = 'a3f8c1e64b52'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'pin_resets',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column(
            'expires_at', sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_pin_resets_email', 'pin_resets', ['email'])
    op.create_index(
        'ix_pin_resets_token_hash', 'pin_resets',
        ['token_hash'], unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_pin_resets_token_hash', table_name='pin_resets')
    op.drop_index('ix_pin_resets_email', table_name='pin_resets')
    op.drop_table('pin_resets')
