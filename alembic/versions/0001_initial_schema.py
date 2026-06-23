"""initial schema

Baseline migration. Enables the pgvector extension, then creates every
table directly from the ORM metadata so the schema matches the models
exactly. Subsequent migrations use ``--autogenerate``.

Revision ID: 0001
Revises:
Create Date: 2026-06-20

"""
from collections.abc import Sequence

from alembic import op
from app.models import Base

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable pgvector and create all tables."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Drop all tables."""
    Base.metadata.drop_all(bind=op.get_bind())
