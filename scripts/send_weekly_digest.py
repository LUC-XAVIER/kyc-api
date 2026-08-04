"""Send the weekly activity digest to every MFI that opted in.

No scheduler runs in-process; invoke this weekly from cron. Example (Mondays
07:00, inside the api container's environment):

    0 7 * * 1  cd /app && uv run python -m scripts.send_weekly_digest

Accounts are skipped when they are not ACTIVE, have the ``weekly`` preference
off, or had no verification activity in the window. With email disabled (dev)
the bodies are logged rather than sent.
"""

from app.db.session import SessionLocal
from app.models import MfiAccount
from app.models.enums import MfiStatus
from app.services import notifications


def main() -> None:
    """Send the digest to every opted-in, active MFI with recent activity."""
    db = SessionLocal()
    sent = 0
    try:
        accounts = (
            db.query(MfiAccount)
            .filter(MfiAccount.status == MfiStatus.ACTIVE)
            .all()
        )
        for account in accounts:
            if not notifications.pref_enabled(account, "weekly"):
                continue
            if notifications.send_weekly_digest_for(db, account):
                sent += 1
    finally:
        db.close()
    print(f"weekly digest: {sent} email(s) sent")


if __name__ == "__main__":
    main()
