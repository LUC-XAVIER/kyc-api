"""add users.failed_login_count / locked_until for login throttling

Revision ID: a1c4e7b20d93
Revises: f5c8d1a92e60
Create Date: 2026-07-16 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1c4e7b20d93'
down_revision: str | None = 'f5c8d1a92e60'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default backfills existing rows; the model-side default only
    # applies to rows the ORM creates.
    op.add_column(
        'users',
        sa.Column(
            'failed_login_count',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
    )
    op.add_column(
        'users',
        sa.Column(
            'locked_until',
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_count')
