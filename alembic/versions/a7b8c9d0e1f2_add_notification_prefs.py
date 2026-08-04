"""add notification preferences + quota-warning flag to mfi_accounts

Revision ID: a7b8c9d0e1f2
Revises: f5a6b7c8d9e0
Create Date: 2026-08-04 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: str | None = 'f5a6b7c8d9e0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Which email alerts the MFI wants (quota / weekly / maintenance).
    # Null means "use the code defaults".
    op.add_column(
        'mfi_accounts',
        sa.Column('notification_prefs', sa.JSON(), nullable=True),
    )
    # One-shot guard so the 80%-quota warning is emailed once per period.
    op.add_column(
        'mfi_accounts',
        sa.Column(
            'quota_warning_sent',
            sa.Boolean(),
            nullable=False,
            server_default='false',
        ),
    )


def downgrade() -> None:
    op.drop_column('mfi_accounts', 'quota_warning_sent')
    op.drop_column('mfi_accounts', 'notification_prefs')
