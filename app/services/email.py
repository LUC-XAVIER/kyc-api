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


def send_email(
    to: str, subject: str, body: str, html: str | None = None
) -> None:
    """Send (or, in dev, log) an email.

    ``body`` is the plain-text version, always included as a fallback. When
    ``html`` is given it is attached as an alternative, so mail clients that
    render HTML show it — and its links are clickable without copy-pasting.
    """
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
    if html is not None:
        msg.add_alternative(html, subtype="html")
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


def _action_html(intro: str, button_label: str, link: str, note: str) -> str:
    """Build a minimal branded HTML email.

    A line of intro, a clickable button, then a note. Inline styles only —
    email clients strip <style> blocks. The raw link is shown too, so it
    works even if the button is stripped.
    """
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;'
        'max-width:480px;margin:0 auto;padding:24px">'
        '<div style="font-size:20px;font-weight:700;color:#c0392b;'
        'margin-bottom:16px">KYC-API</div>'
        f'<p style="font-size:15px;line-height:1.5">{intro}</p>'
        f'<p style="margin:24px 0"><a href="{link}" '
        'style="background:#c0392b;color:#fff;text-decoration:none;'
        'padding:12px 24px;border-radius:6px;font-weight:600;'
        f'display:inline-block">{button_label}</a></p>'
        '<p style="font-size:13px;color:#666;line-height:1.5">'
        f'If the button doesn\'t work, paste this link into your browser:<br>'
        f'<a href="{link}" style="color:#c0392b">{link}</a></p>'
        f'<p style="font-size:13px;color:#666">{note}</p>'
        '</div>'
    )


def send_signup_invite(to: str, token: str) -> None:
    """Email a manager the link to complete their account signup."""
    link = signup_link(token)
    expiry = f"This link expires in {settings.signup_token_ttl_hours} hours."
    send_email(
        to,
        "Complete your KYC-API account setup",
        "Welcome to KYC-API.\n\n"
        f"Finish setting up your account here:\n{link}\n\n{expiry}",
        html=_action_html(
            "Welcome to KYC-API. Click below to finish setting up your "
            "account.",
            "Complete setup",
            link,
            expiry,
        ),
    )


def send_pin_reset(to: str, token: str) -> None:
    """Email a manager the link to reset their PIN."""
    link = reset_link(token)
    expiry = (
        f"This link expires in {settings.reset_token_ttl_hours} hours. "
        "If you didn't request this, you can ignore this email."
    )
    send_email(
        to,
        "Reset your KYC-API PIN",
        "We received a request to reset your PIN.\n\n"
        f"Set a new PIN here:\n{link}\n\n{expiry}",
        html=_action_html(
            "We received a request to reset your PIN. Click below to set a "
            "new one.",
            "Reset PIN",
            link,
            expiry,
        ),
    )
