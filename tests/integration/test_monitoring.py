"""Integration tests for the drift-monitoring endpoint."""

import importlib.util
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import FaceMatchResult, Verification
from app.models.enums import SubmissionMethod, VerificationStatus
from tests.factories import create_mfi_with_key

DRIFT_URL = "/api/v1/kyc/monitoring/drift"

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("evidently") is None,
    reason="requires the optional `ml` extra (Evidently)",
)


def _auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def _seed_scores(db: Session, mfi_id, scores, when: datetime) -> None:
    for score in scores:
        verification = Verification(
            client_id="C",
            mfi_account_id=mfi_id,
            submission_method=SubmissionMethod.API,
            status=VerificationStatus.VERIFIED,
            created_at=when,
            processed_at=when,
        )
        db.add(verification)
        db.flush()
        db.add(
            FaceMatchResult(
                verification_id=verification.id,
                match_score=float(score),
                verified=True,
                threshold=0.4,
            )
        )
    db.flush()


def test_insufficient_data_reports_not_enough(
    api_client: TestClient, db_session: Session
) -> None:
    """With too few scores, the report says data is insufficient."""
    _, key = create_mfi_with_key(db_session, usage=0)

    resp = api_client.get(DRIFT_URL, headers=_auth(key))

    assert resp.status_code == 200
    body = resp.json()
    assert body["sufficient_data"] is False
    assert body["drift_detected"] is False


def test_detects_drift_across_windows(
    api_client: TestClient, db_session: Session
) -> None:
    """A shift between the reference and current windows is flagged."""
    import numpy as np

    account, key = create_mfi_with_key(db_session, usage=0)
    now = datetime.now(UTC)
    rng = np.random.default_rng(0)
    reference = rng.normal(0.8, 0.05, 25).clip(0, 1)
    current = rng.normal(0.4, 0.10, 25).clip(0, 1)
    _seed_scores(db_session, account.id, reference, now - timedelta(days=45))
    _seed_scores(db_session, account.id, current, now - timedelta(days=10))

    resp = api_client.get(
        DRIFT_URL, params={"window_days": 30}, headers=_auth(key)
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["sufficient_data"] is True
    assert body["reference_size"] == 25
    assert body["current_size"] == 25
    assert body["drift_detected"] is True


def test_requires_authentication(api_client: TestClient) -> None:
    """Drift monitoring needs an API key."""
    assert api_client.get(DRIFT_URL).status_code == 401
