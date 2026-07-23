"""make users.mfi_account_id nullable for the platform admin

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-07-23 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd3e4f5a6b7c8'
down_revision: str | None = 'c2d3e4f5a6b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A platform admin (role ADMIN) oversees every MFI and belongs to none,
    # so its mfi_account_id is null; all MFI staff still carry theirs.
    op.alter_column(
        'users', 'mfi_account_id', existing_type=sa.Uuid(), nullable=True
    )


def downgrade() -> None:
    op.alter_column(
        'users', 'mfi_account_id', existing_type=sa.Uuid(), nullable=False
    )
