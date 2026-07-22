"""add review_reason and reviewed_at to verifications

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-07-22 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: str | None = 'b1c2d3e4f5a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'verifications',
        sa.Column('review_reason', sa.String(length=500), nullable=True),
    )
    op.add_column(
        'verifications',
        sa.Column(
            'reviewed_at', sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column('verifications', 'reviewed_at')
    op.drop_column('verifications', 'review_reason')
