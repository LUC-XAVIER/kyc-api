"""Send one test email with the current SMTP settings, to check delivery.

Useful after configuring a mail provider: it sends a real message and tells
you whether the send succeeded, so you can then check the inbox (and spam).

    python -m scripts.send_test_email you@example.com
"""

import sys

from app.core.config import settings
from app.services.email import send_email


def main() -> None:
    """Send a test email to the address given on the command line."""
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.send_test_email <recipient-email>")
        raise SystemExit(1)
    to = sys.argv[1]

    print("Current mail settings:")
    print(f"  email_enabled = {settings.email_enabled}")
    print(f"  smtp_host     = {settings.smtp_host}")
    print(f"  smtp_port     = {settings.smtp_port}")
    print(f"  smtp_user     = {settings.smtp_user}")
    print(f"  email_from    = {settings.email_from}")

    if not (settings.email_enabled and settings.smtp_user):
        print(
            "\nEmail is OFF (email_enabled is false or no SMTP user). "
            "Set EMAIL_ENABLED=true and the SMTP_* values, then retry."
        )
        raise SystemExit(1)

    send_email(
        to,
        "KYC-API test email",
        "If you can read this, KYC-API email delivery is working.",
    )
    print(f"\nSent with no error. Now check {to} — look in spam/junk too.")


if __name__ == "__main__":
    main()
