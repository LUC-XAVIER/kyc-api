"""Outbound email (signup invites, PIN resets).

In development (``email_enabled=False`` or no SMTP user) messages are logged
rather than sent, and the onboarding endpoints return the link directly so
the flow can be exercised without a mail server. Set ``email_enabled=true``
plus SMTP credentials to send real mail.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings
from app.core.exceptions import EmailError

logger = logging.getLogger("app.email")


def _enabled() -> bool:
    return settings.email_enabled and bool(settings.smtp_user)


def send_email(to: str, subject: str, body: str) -> None:
    """Send (or, in dev, log) a plain-text email."""
    if not _enabled():
        logger.info(
            "EMAIL (dev — not sent)\n  to: %s\n  subject: %s\n%s",
            to, subject, body,
        )
        return

    msg = EmailMessage()
    msg["From"] = settings.email_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    # Gmail shows App Passwords grouped with spaces; strip them for login.
    password = settings.smtp_password.replace(" ", "")
    try:
        with smtplib.SMTP(
            settings.smtp_host, settings.smtp_port, timeout=15
        ) as server:
            server.starttls()
            server.login(settings.smtp_user, password)
            server.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("SMTP send to %s failed: %s", to, exc)
        raise EmailError(
            "Could not send the email — check the SMTP settings "
            "(Gmail requires a 16-character App Password)."
        ) from exc


def signup_link(token: str) -> str:
    """Return the dashboard signup URL carrying the invite token."""
    return f"{settings.dashboard_url}/signup?token={token}"


def reset_link(token: str) -> str:
    """Return the dashboard PIN-reset URL carrying the reset token."""
    return f"{settings.dashboard_url}/reset-pin?token={token}"


def send_signup_invite(to: str, token: str) -> None:
    """Email a manager the link to complete their account signup."""
    link = signup_link(token)
    send_email(
        to,
        "Complete your KYC-API account setup",
        "Welcome to KYC-API.\n\n"
        f"Finish setting up your account here:\n{link}\n\n"
        f"This link expires in {settings.signup_token_ttl_hours} hours.",
    )


def send_pin_reset(to: str, token: str) -> None:
    """Email a manager the link to reset their PIN."""
    link = reset_link(token)
    send_email(
        to,
        "Reset your KYC-API PIN",
        "We received a request to reset your PIN.\n\n"
        f"Set a new PIN here:\n{link}\n\n"
        f"This link expires in {settings.reset_token_ttl_hours} hours. "
        "If you didn't request this, you can ignore this email.",
    )
