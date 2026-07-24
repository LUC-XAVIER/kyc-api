"""Seed the platform-admin account (dev / bootstrap / deploy).

Creates the single cross-tenant ``ADMIN`` who oversees every MFI. Unlike a
manager or agent, the admin belongs to no MFI (``mfi_account_id`` is null).

Safe to run on every deploy: if the admin already exists it is left as-is
(its PIN is **not** reset, so a PIN changed from the dashboard survives).
Pass ``--force`` to reset the PIN **and clear 2FA** of an existing admin —
the break-glass recovery for a lost authenticator.

Credentials come from ``--email`` / ``--pin`` or the ``ADMIN_EMAIL`` /
``ADMIN_PIN`` env vars, falling back to the bootstrap defaults.

Run (after `docker compose up -d db` and `alembic upgrade head`):

    uv run python -m scripts.seed_admin
    uv run python -m scripts.seed_admin --email admin@site.com --pin 246810
    uv run python -m scripts.seed_admin --force   # reset an existing PIN
"""

import argparse
import os

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User
from app.models.enums import AgentRole, AgentStatus


def main() -> None:
    """Create (or ensure) the platform admin and print its status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--email", default=os.getenv("ADMIN_EMAIL", "zazap1731@gmail.com")
    )
    parser.add_argument("--pin", default=os.getenv("ADMIN_PIN", "123456"))
    parser.add_argument(
        "--name", default=os.getenv("ADMIN_NAME", "KYC-API Admin")
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="reset the PIN even if the admin already exists",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        admin = db.query(User).filter_by(email=args.email).one_or_none()
        created = admin is None
        if created:
            admin = User(full_name=args.name, mfi_account_id=None)
            db.add(admin)
        # Always keep the identity/role consistent; only (re)set the PIN when
        # creating a fresh account or when explicitly forced.
        admin.email = args.email
        admin.role = AgentRole.ADMIN
        admin.status = AgentStatus.ACTIVE
        admin.mfi_account_id = None
        if created:
            admin.full_name = args.name
        if created or args.force:
            admin.hashed_pin = hash_password(args.pin)
        if args.force:
            # Break-glass recovery: also clear 2FA, so a lost authenticator
            # can't lock the admin out permanently (needs host/db access).
            admin.totp_enabled = False
            admin.totp_secret = None

        db.commit()
        if created:
            print(
                f"Platform admin created — sign in with email={args.email} "
                f"pin={args.pin}"
            )
        elif args.force:
            print(
                f"Platform admin reset (PIN + 2FA cleared) — "
                f"email={args.email}"
            )
        else:
            print(
                f"Platform admin already exists — email={args.email} "
                "(PIN unchanged)"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
