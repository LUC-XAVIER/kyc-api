"""add verification_images

Revision ID: b1c2d3e4f5a6
Revises: 8beaaa5a9d0c
Create Date: 2026-07-21 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: str | None = '8beaaa5a9d0c'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'verification_images',
        sa.Column('verification_id', sa.Uuid(), nullable=False),
        sa.Column(
            'kind',
            sa.Enum('ID_FRONT', 'ID_BACK', 'SELFIE', name='image_kind'),
            nullable=False,
        ),
        sa.Column('content_type', sa.String(length=32), nullable=False),
        sa.Column('image', sa.LargeBinary(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['verification_id'],
            ['verifications.id'],
            name=op.f(
                'fk_verification_images_verification_id_verifications'
            ),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_verification_images')),
    )
    op.create_index(
        op.f('ix_verification_images_verification_id'),
        'verification_images',
        ['verification_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_verification_images_verification_id'),
        table_name='verification_images',
    )
    op.drop_table('verification_images')
    op.execute('DROP TYPE IF EXISTS image_kind')
