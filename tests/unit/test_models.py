"""Schema-level checks that need no database connection."""

from sqlalchemy.schema import CreateTable

from app.db.base import EMBEDDING_DIM
from app.models import Base

EXPECTED_TABLES = {
    "subscription_plans",
    "mfi_accounts",
    "users",
    "branches",
    "signup_invites",
    "pin_resets",
    "api_keys",
    "verifications",
    "extracted_data",
    "face_embeddings",
    "liveness_results",
    "face_match_results",
    "duplicate_flags",
    "audit_logs",
    "compliance_reports",
}


def test_all_entities_registered() -> None:
    """Every mapped entity is registered to a table."""
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_face_embedding_vector_dimension() -> None:
    """The embedding column is a pgvector column of the ArcFace dimension."""
    vector_col = Base.metadata.tables["face_embeddings"].c.vector
    assert vector_col.type.dim == EMBEDDING_DIM == 512


def test_tenant_owned_rows_carry_account_id() -> None:
    """Tenant-scoped tables expose mfi_account_id for multi-tenancy."""
    for table in (
        "verifications",
        "users",
        "api_keys",
        "audit_logs",
        "compliance_reports",
    ):
        assert "mfi_account_id" in Base.metadata.tables[table].c


def test_tables_compile_to_postgres_ddl() -> None:
    """Every table renders valid PostgreSQL DDL (offline)."""
    from sqlalchemy.dialects import postgresql

    pg = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        assert "CREATE TABLE" in str(CreateTable(table).compile(dialect=pg))
