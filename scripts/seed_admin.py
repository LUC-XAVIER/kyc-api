"""Seed the Openxtech platform-admin account (dev / bootstrap).

Creates (or refreshes) the single cross-tenant ``ADMIN`` who oversees every
MFI. Unlike a manager or agent, the admin belongs to no MFI
(``mfi_account_id`` is null). Idempotent — re-running just resets the PIN.

Run (after `docker compose up -d db` and `alembic upgrade head`):

    uv run python -m scripts.seed_admin
    uv run python -m scripts.seed_admin --email admin@openxtech.cm --pin 246810
"""

import argparse

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User
from app.models.enums import AgentRole, AgentStatus


def main() -> None:
    """Create/refresh the platform admin and print the login credentials."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", default="zazap1731@gmail.com")
    parser.add_argument("--pin", default="123456")
    parser.add_argument("--name", default="Admin Openxtech")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(email=args.email).one_or_none()
        if admin is None:
            admin = User(full_name=args.name, mfi_account_id=None)
            db.add(admin)
        admin.email = args.email
        admin.full_name = args.name
        admin.hashed_pin = hash_password(args.pin)
        admin.role = AgentRole.ADMIN
        admin.status = AgentStatus.ACTIVE
        admin.mfi_account_id = None

        db.commit()
        print(
            f"Platform admin ready — sign in with email={args.email} "
            f"pin={args.pin}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
