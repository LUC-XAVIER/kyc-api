"""Unit tests for the email service (dev-mode / link building)."""

from app.services import email


def test_signup_link_carries_the_token():
    """The signup link embeds the raw token as a query param."""
    assert email.signup_link("abc123").endswith("/signup?token=abc123")


def test_reset_link_carries_the_token():
    """The reset link embeds the raw token as a query param."""
    assert email.reset_link("xyz789").endswith("/reset-pin?token=xyz789")


def test_send_email_in_dev_mode_does_not_raise():
    """With email disabled the message is logged, not sent (no error)."""
    email.send_email("someone@example.com", "Subject", "Body")
