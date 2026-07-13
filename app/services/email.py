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
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)


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
