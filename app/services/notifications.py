"""Manager notification preferences and email triggers.

The manager Settings screen exposes four toggles. One — "New PENDING case" —
is handled in-app (a toast). The other three are email alerts orchestrated
here:

* ``quota``       — one warning when usage first crosses the 80% threshold.
* ``weekly``      — a digest of the last 7 days (sent by a scheduled script).
* ``maintenance`` — a broadcast an admin sends from the admin dashboard.

Preferences are stored on :class:`MfiAccount.notification_prefs` (JSON); a null
value means "use :data:`NOTIF_DEFAULTS`". This module owns *who* and *when*;
:mod:`app.services.email` owns the message bodies and the actual send.
"""

import logging

from sqlalchemy.orm import Session

from app.core.exceptions import EmailError
from app.models import MfiAccount
from app.services import email as email_service
from app.services.subscription import QuotaStatus

logger = logging.getLogger("app.notifications")

# Mirrors the frontend defaults (manager.component.ts NOTIF_DEFAULTS).
NOTIF_DEFAULTS: dict[str, bool] = {
    "quota": True,
    "pending": True,
    "weekly": False,
    "maintenance": True,
}
NOTIF_KEYS = frozenset(NOTIF_DEFAULTS)


def get_prefs(account: MfiAccount) -> dict[str, bool]:
    """Return the account's notification prefs, defaults filling any gaps."""
    stored = account.notification_prefs or {}
    return {key: bool(stored.get(key, default))
            for key, default in NOTIF_DEFAULTS.items()}


def pref_enabled(account: MfiAccount, key: str) -> bool:
    """Whether ``account`` wants the ``key`` notification (default-aware)."""
    return get_prefs(account)[key]


def sanitize_prefs(raw: dict) -> dict[str, bool]:
    """Coerce a client payload to a clean {known_key: bool} dict."""
    return {key: bool(value)
            for key, value in raw.items()
            if key in NOTIF_KEYS}


def maybe_send_quota_warning(
    session: Session, account: MfiAccount, quota: QuotaStatus
) -> None:
    """Email the 80%-quota warning once per period, if the MFI wants it.

    Called after a verification is recorded. Guarded by
    ``account.quota_warning_sent`` so it fires a single time each billing
    period (the flag is reset in ``subscription.roll_period_if_needed``). A
    failed send is logged, never raised — it must not break verification.
    """
    if account.quota_warning_sent or not quota.warning or quota.exhausted:
        return
    if not pref_enabled(account, "quota"):
        return
    try:
        email_service.send_quota_warning(
            account.email, used=quota.used, limit=quota.limit
        )
    except EmailError:
        logger.exception("quota-warning email to %s failed", account.email)
        return
    account.quota_warning_sent = True
    session.commit()
