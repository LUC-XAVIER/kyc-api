"""add payments table

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-07-28 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f5a6b7c8d9e0'
down_revision: str | None = 'e4f5a6b7c8d9'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # plan_name already exists (subscription_plans uses it) — reference it
    # without re-creating. The two new enums are created here.
    plan_name = postgresql.ENUM(
        'STARTER', 'GROWTH', 'PRO', 'ENTERPRISE',
        name='plan_name',
        create_type=False,
    )
    op.create_table(
        'payments',
        sa.Column('mfi_account_id', sa.Uuid(), nullable=False),
        sa.Column('plan_name', plan_name, nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=8), nullable=False),
        sa.Column('phone', sa.String(length=32), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'PENDING', 'SUCCESSFUL', 'FAILED', name='payment_status'
            ),
            nullable=False,
        ),
        sa.Column(
            'provider',
            sa.Enum('CAMPAY', 'MOCK', name='payment_provider'),
            nullable=False,
        ),
        sa.Column(
            'external_reference', sa.String(length=64), nullable=False
        ),
        sa.Column(
            'provider_reference', sa.String(length=128), nullable=True
        ),
        sa.Column('ussd_code', sa.String(length=32), nullable=True),
        sa.Column('failure_reason', sa.String(length=255), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['mfi_account_id'],
            ['mfi_accounts.id'],
            name=op.f('fk_payments_mfi_account_id_mfi_accounts'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_payments')),
        sa.UniqueConstraint(
            'external_reference', name=op.f('uq_payments_external_reference')
        ),
    )
    op.create_index(
        op.f('ix_payments_mfi_account_id'),
        'payments',
        ['mfi_account_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_payments_mfi_account_id'), table_name='payments')
    op.drop_table('payments')
    op.execute('DROP TYPE IF EXISTS payment_status')
    op.execute('DROP TYPE IF EXISTS payment_provider')
