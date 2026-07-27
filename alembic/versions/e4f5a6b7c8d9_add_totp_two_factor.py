"""add TOTP two-factor columns to users

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-24 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e4f5a6b7c8d9'
down_revision: str | None = 'd3e4f5a6b7c8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # totp_secret holds the AES-GCM-encrypted base32 secret. Like every
    # EncryptedString column it is stored as BYTEA (LargeBinary), not text.
    op.add_column(
        'users', sa.Column('totp_secret', sa.LargeBinary(), nullable=True)
    )
    op.add_column(
        'users',
        sa.Column(
            'totp_enabled',
            sa.Boolean(),
            nullable=False,
            server_default='false',
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_secret')
