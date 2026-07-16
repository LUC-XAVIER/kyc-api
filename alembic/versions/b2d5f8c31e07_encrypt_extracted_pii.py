"""encrypt the directly identifying extracted_data fields (NFR03/NFR04)

Converts full_name, id_number, date_of_birth and place_of_birth from
readable columns to AES-GCM sealed BYTEA. Existing rows are re-encrypted
in place, so ENCRYPTION_KEY must be set before running this — and must be
the same key the application will later read with.

Revision ID: b2d5f8c31e07
Revises: a1c4e7b20d93
Create Date: 2026-07-16 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.crypto import decrypt, encrypt

# revision identifiers, used by Alembic.
revision: str = 'b2d5f8c31e07'
down_revision: str | None = 'a1c4e7b20d93'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (column, old type, whether the value is a date rather than text)
_FIELDS = (
    ('full_name', sa.String(255), False),
    ('id_number', sa.String(64), False),
    ('date_of_birth', sa.Date(), True),
    ('place_of_birth', sa.String(255), False),
)


def upgrade() -> None:
    conn = op.get_bind()

    for name, _old_type, _is_date in _FIELDS:
        op.add_column(
            'extracted_data',
            sa.Column(f'{name}_enc', sa.LargeBinary(), nullable=True),
        )

    # Re-encrypt row by row in Python: the sealing cannot be expressed in
    # SQL, and the table is small (one row per verification).
    cols = ', '.join(name for name, _t, _d in _FIELDS)
    rows = conn.execute(
        sa.text(f'SELECT id, {cols} FROM extracted_data')
    ).fetchall()

    for row in rows:
        values = {'row_id': row.id}
        for name, _old_type, is_date in _FIELDS:
            plain = getattr(row, name)
            if plain is None:
                values[name] = None
            elif is_date:
                values[name] = encrypt(plain.isoformat().encode())
            else:
                values[name] = encrypt(plain.encode())
        assignments = ', '.join(
            f'{name}_enc = :{name}' for name, _t, _d in _FIELDS
        )
        conn.execute(
            sa.text(
                f'UPDATE extracted_data SET {assignments} WHERE id = :row_id'
            ),
            values,
        )

    for name, _old_type, _is_date in _FIELDS:
        op.drop_column('extracted_data', name)
        op.alter_column('extracted_data', f'{name}_enc', new_column_name=name)


def downgrade() -> None:
    """Decrypt back to readable columns.

    Requires the same ENCRYPTION_KEY the data was sealed with; without it
    the values are unrecoverable and this will fail rather than destroy
    them silently.
    """
    conn = op.get_bind()

    for name, old_type, _is_date in _FIELDS:
        op.add_column(
            'extracted_data', sa.Column(f'{name}_dec', old_type, nullable=True)
        )

    cols = ', '.join(name for name, _t, _d in _FIELDS)
    rows = conn.execute(
        sa.text(f'SELECT id, {cols} FROM extracted_data')
    ).fetchall()

    for row in rows:
        values = {'row_id': row.id}
        for name, _old_type, is_date in _FIELDS:
            sealed = getattr(row, name)
            if sealed is None:
                values[name] = None
            else:
                plain = decrypt(bytes(sealed)).decode()
                values[name] = (
                    sa.Date().python_type.fromisoformat(plain)
                    if is_date
                    else plain
                )
        assignments = ', '.join(
            f'{name}_dec = :{name}' for name, _t, _d in _FIELDS
        )
        conn.execute(
            sa.text(
                f'UPDATE extracted_data SET {assignments} WHERE id = :row_id'
            ),
            values,
        )

    for name, _old_type, _is_date in _FIELDS:
        op.drop_column('extracted_data', name)
        op.alter_column('extracted_data', f'{name}_dec', new_column_name=name)
