"""Mobile-money payment gateway clients (Campay + a dev mock).

Isolates the HTTP details of collecting money from the business logic in
:mod:`app.services.payments`. Two implementations satisfy the same small
interface, chosen at runtime by ``settings.payments_enabled``:

* :class:`CampayProvider` — talks to Campay (MTN MoMo + Orange Money) over
  its REST API. Sandbox and production differ only by ``campay_base_url``.
* :class:`MockProvider` — no network; deterministically simulates the
  collection so the whole feature is testable without a merchant account.
  A payer phone ending in ``0000`` simulates a decline, anything else a
  success, so both branches are exercisable in dev and tests.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx
import jwt

from app.core.config import settings
from app.models.enums import PaymentProvider, PaymentStatus

# Campay status strings → our enum. Anything else is treated as pending.
_CAMPAY_STATUS = {
    "SUCCESSFUL": PaymentStatus.SUCCESSFUL,
    "FAILED": PaymentStatus.FAILED,
    "PENDING": PaymentStatus.PENDING,
}
_MOCK_FAIL_SUFFIX = "0000"
_HTTP_TIMEOUT = 30.0


@dataclass(frozen=True)
class CollectionResult:
    """Outcome of initiating a collection (before the payer has acted)."""

    provider_reference: str
    status: PaymentStatus
    ussd_code: str | None = None


@dataclass(frozen=True)
class StatusResult:
    """A payment's current status as reported by the provider."""

    status: PaymentStatus
    failure_reason: str | None = None


class CampayProvider:
    """Client for the Campay collection API (real money)."""

    name = PaymentProvider.CAMPAY

    def __init__(self) -> None:
        """Bind the client to the configured base URL and access token."""
        self._base = settings.campay_base_url.rstrip("/")
        self._headers = {"Authorization": f"Token {settings.campay_token}"}

    def initiate_collection(
        self,
        *,
        amount: int,
        currency: str,
        phone: str,
        external_reference: str,
        description: str,
    ) -> CollectionResult:
        """Ask Campay to prompt the payer for ``amount`` on their phone."""
        payload = {
            "amount": str(amount),
            "currency": currency,
            "from": phone,
            "description": description,
            "external_reference": external_reference,
        }
        data = self._post("/collect/", payload)
        return CollectionResult(
            provider_reference=data["reference"],
            status=PaymentStatus.PENDING,
            ussd_code=data.get("ussd_code"),
        )

    def get_status(
        self, *, provider_reference: str, phone: str
    ) -> StatusResult:
        """Poll Campay for the current state of a collection.

        ``phone`` is unused here (Campay keys on its own reference); it keeps
        the signature uniform with the mock so callers never branch on the
        provider.
        """
        data = self._get(f"/transaction/{provider_reference}/")
        status = _CAMPAY_STATUS.get(
            data.get("status", ""), PaymentStatus.PENDING
        )
        reason = data.get("reason")
        return StatusResult(
            status=status,
            failure_reason=reason if status is PaymentStatus.FAILED else None,
        )

    def verify_webhook(self, params: dict[str, str]) -> bool:
        """Validate a Campay webhook by checking its signed ``signature``.

        Campay signs each callback as a JWT (HS256) with the app's webhook
        key; a payload that decodes cleanly proves it really came from
        Campay and was not tampered with in transit.
        """
        token = params.get("signature")
        if not token or not settings.campay_webhook_key:
            return False
        try:
            jwt.decode(
                token,
                settings.campay_webhook_key,
                algorithms=["HS256"],
            )
        except jwt.InvalidTokenError:
            return False
        return True

    def _post(self, path: str, json: dict) -> dict:
        resp = httpx.post(
            f"{self._base}{path}",
            json=json,
            headers=self._headers,
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()

    def _get(self, path: str) -> dict:
        resp = httpx.get(
            f"{self._base}{path}",
            headers=self._headers,
            timeout=_HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()


class MockProvider:
    """Deterministic, network-free stand-in for local dev and tests."""

    name = PaymentProvider.MOCK

    def initiate_collection(
        self,
        *,
        amount: int,
        currency: str,
        phone: str,
        external_reference: str,
        description: str,
    ) -> CollectionResult:
        """Pretend to prompt the payer; always starts PENDING."""
        return CollectionResult(
            provider_reference=f"mock-{uuid.uuid4().hex[:16]}",
            status=PaymentStatus.PENDING,
            ussd_code="*126#",
        )

    def get_status(
        self, *, provider_reference: str, phone: str
    ) -> StatusResult:
        """Settle from the payer phone so both paths are testable in dev.

        A number ending in ``0000`` simulates a decline; anything else
        succeeds.
        """
        if phone.endswith(_MOCK_FAIL_SUFFIX):
            return StatusResult(
                status=PaymentStatus.FAILED,
                failure_reason="Simulated decline (mock).",
            )
        return StatusResult(status=PaymentStatus.SUCCESSFUL)

    def verify_webhook(self, params: dict[str, str]) -> bool:
        """The mock has no real signature; callbacks are trusted in dev."""
        return True


def get_provider() -> CampayProvider | MockProvider:
    """Return the active provider based on configuration."""
    return CampayProvider() if settings.payments_enabled else MockProvider()
