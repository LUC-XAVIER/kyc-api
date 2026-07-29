"""Integration tests for subscription payments (mock provider).

``payments_enabled`` is False in tests, so the network-free MockProvider is
used: a payer phone ending in ``0000`` simulates a decline, anything else a
success. That lets both branches run without a real merchant account.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Payment
from app.models.enums import AgentRole, MfiStatus, PaymentStatus
from tests.factories import create_agent, create_mfi_with_key

SUBSCRIBE = "/api/v1/payments/subscribe"
PAYMENTS = "/api/v1/payments"
WEBHOOK = "/api/v1/payments/webhook"


def _manager(db: Session, mfi, email: str):
    """Create a manager and return its bearer headers."""
    agent = create_agent(db, mfi, email=email, role=AgentRole.MANAGER)
    token = create_access_token(subject=str(agent.id), role="MANAGER")
    return {"Authorization": f"Bearer {token}"}


def test_subscribe_starts_a_pending_payment(
    api_client: TestClient, db_session: Session
) -> None:
    """A manager starts a plan payment; it begins PENDING with a USSD code."""
    mfi, _ = create_mfi_with_key(db_session, email="a@x.cm")
    headers = _manager(db_session, mfi, "mgr@a.cm")

    resp = api_client.post(
        SUBSCRIBE,
        json={"plan": "GROWTH", "phone": "677123456"},
        headers=headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PENDING"
    assert body["plan_name"] == "GROWTH"
    assert body["amount"] == 65000
    assert body["provider"] == "MOCK"
    assert body["ussd_code"]


def test_poll_success_activates_the_subscription(
    api_client: TestClient, db_session: Session
) -> None:
    """Polling a successful payment flips the MFI to the paid plan."""
    mfi, _ = create_mfi_with_key(db_session, email="b@x.cm")
    mfi.status = MfiStatus.PENDING
    headers = _manager(db_session, mfi, "mgr@b.cm")

    started = api_client.post(
        SUBSCRIBE,
        json={"plan": "PRO", "phone": "677123456"},
        headers=headers,
    ).json()

    resp = api_client.get(f"{PAYMENTS}/{started['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "SUCCESSFUL"

    db_session.refresh(mfi)
    assert mfi.status == MfiStatus.ACTIVE
    assert mfi.plan.name.value == "PRO"
    assert mfi.current_period_usage == 0


def test_poll_failure_does_not_activate(
    api_client: TestClient, db_session: Session
) -> None:
    """A declined payment (phone ending 0000) leaves the account untouched."""
    mfi, _ = create_mfi_with_key(db_session, email="c@x.cm")
    mfi.status = MfiStatus.PENDING
    headers = _manager(db_session, mfi, "mgr@c.cm")

    started = api_client.post(
        SUBSCRIBE,
        json={"plan": "STARTER", "phone": "677120000"},
        headers=headers,
    ).json()

    resp = api_client.get(f"{PAYMENTS}/{started['id']}", headers=headers)
    assert resp.json()["status"] == "FAILED"
    assert resp.json()["failure_reason"]

    db_session.refresh(mfi)
    assert mfi.status == MfiStatus.PENDING


def test_enterprise_plan_is_not_self_payable(
    api_client: TestClient, db_session: Session
) -> None:
    """The custom-priced plan cannot be paid online -> 400."""
    mfi, _ = create_mfi_with_key(db_session, email="d@x.cm")
    headers = _manager(db_session, mfi, "mgr@d.cm")

    resp = api_client.post(
        SUBSCRIBE,
        json={"plan": "ENTERPRISE", "phone": "677123456"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_agent_cannot_subscribe(
    api_client: TestClient, db_session: Session
) -> None:
    """A plain agent may not start a payment -> 403."""
    mfi, _ = create_mfi_with_key(db_session, email="e@x.cm")
    agent = create_agent(db_session, mfi, role=AgentRole.AGENT)
    token = create_access_token(subject=str(agent.id), role="AGENT")

    resp = api_client.post(
        SUBSCRIBE,
        json={"plan": "GROWTH", "phone": "677123456"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_payment_is_scoped_to_its_mfi(
    api_client: TestClient, db_session: Session
) -> None:
    """One MFI cannot read another MFI's payment -> 404."""
    mfi_a, _ = create_mfi_with_key(db_session, email="f@x.cm")
    headers_a = _manager(db_session, mfi_a, "mgr@f.cm")
    started = api_client.post(
        SUBSCRIBE,
        json={"plan": "GROWTH", "phone": "677123456"},
        headers=headers_a,
    ).json()

    mfi_b, _ = create_mfi_with_key(db_session, email="g@x.cm")
    headers_b = _manager(db_session, mfi_b, "mgr@g.cm")
    resp = api_client.get(f"{PAYMENTS}/{started['id']}", headers=headers_b)
    assert resp.status_code == 404


def test_webhook_settles_and_is_idempotent(
    api_client: TestClient, db_session: Session
) -> None:
    """A success webhook activates once; a duplicate changes nothing."""
    mfi, _ = create_mfi_with_key(db_session, email="h@x.cm")
    mfi.status = MfiStatus.PENDING
    headers = _manager(db_session, mfi, "mgr@h.cm")
    started = api_client.post(
        SUBSCRIBE,
        json={"plan": "GROWTH", "phone": "677120000"},
        headers=headers,
    ).json()

    payload = {
        "status": "SUCCESSFUL",
        "external_reference": _reference(db_session, started["id"]),
        "reference": "op-123",
    }
    first = api_client.post(WEBHOOK, json=payload)
    assert first.status_code == 200
    assert first.json()["status"] == "ok"
    db_session.refresh(mfi)
    assert mfi.status == MfiStatus.ACTIVE

    # A duplicate callback is accepted but must not re-settle.
    second = api_client.post(WEBHOOK, json=payload)
    assert second.json()["status"] == "ok"
    payment = db_session.get(Payment, started["id"])
    assert payment.status == PaymentStatus.SUCCESSFUL


def _reference(db: Session, payment_id: str) -> str:
    return db.get(Payment, payment_id).external_reference


def test_pending_account_cannot_verify(
    api_client: TestClient, db_session: Session
) -> None:
    """An unpaid (PENDING) account is blocked from metered use -> 403."""
    mfi, key = create_mfi_with_key(db_session, email="p@x.cm")
    mfi.status = MfiStatus.PENDING
    db_session.flush()

    resp = api_client.post(
        "/api/v1/kyc/verify",
        headers={"X-API-Key": key},
        files={
            "id_front": ("f.jpg", b"x", "image/jpeg"),
            "selfie": ("s.jpg", b"x", "image/jpeg"),
        },
        data={"client_id": "C-1", "document_type": "NIC"},
    )
    assert resp.status_code == 403
    assert "inactive" in resp.json()["error"]["message"].lower()


def test_list_payments_returns_history(
    api_client: TestClient, db_session: Session
) -> None:
    """The MFI can list its own payments."""
    mfi, _ = create_mfi_with_key(db_session, email="i@x.cm")
    headers = _manager(db_session, mfi, "mgr@i.cm")
    api_client.post(
        SUBSCRIBE,
        json={"plan": "GROWTH", "phone": "677123456"},
        headers=headers,
    )
    resp = api_client.get(PAYMENTS, headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
