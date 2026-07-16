"""add branches; move users.branch (text) to branch_id FK

Revision ID: f5c8d1a92e60
Revises: e1b6a2d34c78
Create Date: 2026-07-14 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f5c8d1a92e60'
down_revision: str | None = 'e1b6a2d34c78'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'branches',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at', sa.DateTime(),
            server_default=sa.text('now()'), nullable=False,
        ),
        sa.Column('mfi_account_id', sa.Uuid(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.ForeignKeyConstraint(['mfi_account_id'], ['mfi_accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'mfi_account_id', 'name', name='uq_branches_mfi_name'
        ),
    )
    op.create_index(
        'ix_branches_mfi_account_id', 'branches', ['mfi_account_id']
    )

    op.add_column('users', sa.Column('branch_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_users_branch_id', 'users', 'branches', ['branch_id'], ['id']
    )

    # Backfill: a Branch per distinct (mfi, branch text), then link users.
    op.execute(
        """
        INSERT INTO branches (id, created_at, mfi_account_id, name)
        SELECT gen_random_uuid(), now(), mfi_account_id, branch
        FROM (
            SELECT DISTINCT mfi_account_id, branch
            FROM users WHERE branch IS NOT NULL
        ) d
        """
    )
    op.execute(
        """
        UPDATE users u SET branch_id = b.id
        FROM branches b
        WHERE b.mfi_account_id = u.mfi_account_id AND b.name = u.branch
        """
    )
    op.drop_column('users', 'branch')


def downgrade() -> None:
    op.add_column(
        'users', sa.Column('branch', sa.String(255), nullable=True)
    )
    op.execute(
        "UPDATE users u SET branch = b.name "
        "FROM branches b WHERE b.id = u.branch_id"
    )
    op.drop_constraint('fk_users_branch_id', 'users', type_='foreignkey')
    op.drop_column('users', 'branch_id')
    op.drop_index('ix_branches_mfi_account_id', table_name='branches')
    op.drop_table('branches')
