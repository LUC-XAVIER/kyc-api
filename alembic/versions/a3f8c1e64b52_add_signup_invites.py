"""add signup_invites (self-service manager onboarding)

Revision ID: a3f8c1e64b52
Revises: c2e5a7b91d34
Create Date: 2026-07-12 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3f8c1e64b52'
down_revision: str | None = 'c2e5a7b91d34'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'signup_invites',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('plan', sa.String(32), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column(
            'expires_at', sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            'completed_at', sa.DateTime(timezone=True), nullable=True
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_signup_invites_email', 'signup_invites', ['email']
    )
    op.create_index(
        'ix_signup_invites_token_hash', 'signup_invites',
        ['token_hash'], unique=True,
    )


def downgrade() -> None:
    op.drop_index('ix_signup_invites_token_hash', table_name='signup_invites')
    op.drop_index('ix_signup_invites_email', table_name='signup_invites')
    op.drop_table('signup_invites')
