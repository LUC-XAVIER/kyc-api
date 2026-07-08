"""Integration tests for POST /kyc/verify and quota enforcement.

The ML pipeline is stubbed (run_verification is monkeypatched) so these
exercise the multipart endpoint, persistence, and quota against the real
database without loading models.
"""

import uuid
from datetime import date

import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.routes import verify as verify_route
from app.models import (
    DuplicateFlag,
    ExtractedData,
    FaceEmbedding,
    FaceMatchResult,
    LivenessResult,
)
from app.models.enums import VerificationStatus
from app.pipeline.contracts import (
    DuplicateOutcome,
    FaceMatchOutcome,
    LivenessOutcome,
    OcrResult,
)
from app.pipeline.orchestrator import PipelineResult, VerificationOutput
from tests.factories import create_mfi_with_key

VERIFY_URL = "/api/v1/kyc/verify"


def _auth(key: str) -> dict[str, str]:
    return {"X-API-Key": key}


def _files(*, with_back: bool = True) -> dict:
    image = ("img.png", b"fake-image-bytes", "image/png")
    files = {"id_front": image, "selfie": image}
    if with_back:
        files["id_back"] = image
    return files


def _data(client_id: str, document_type: str = "NIC") -> dict[str, str]:
    return {"client_id": client_id, "document_type": document_type}


def _stub_pipeline(monkeypatch, output: VerificationOutput) -> None:
    monkeypatch.setattr(
        verify_route,
        "run_verification",
        lambda data, *, duplicate_store: output,
    )


def _verified() -> VerificationOutput:
    return VerificationOutput(
        PipelineResult(VerificationStatus.VERIFIED, 0.99),
        np.zeros(512, dtype=np.float32),
    )


def test_verify_succeeds_persists_and_consumes_quota(
    api_client: TestClient, db_session: Session, monkeypatch
) -> None:
    """A clean pass returns 201, enrolls the embedding, and bills one unit."""
    _stub_pipeline(monkeypatch, _verified())
    account, key = create_mfi_with_key(db_session, usage=0)

    resp = api_client.post(
        VERIFY_URL,
        data=_data("CLIENT-001"),
        files=_files(),
        headers=_auth(key),
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == VerificationStatus.VERIFIED.value
    assert body["client_id"] == "CLIENT-001"
    assert body["quota_remaining"] == 199
    assert account.current_period_usage == 1
    assert (
        db_session.query(FaceEmbedding)
        .filter_by(client_id="CLIENT-001")
        .count()
        == 1
    )


def test_verify_rejected_does_not_enroll(
    api_client: TestClient, db_session: Session, monkeypatch
) -> None:
    """A REJECTED result is recorded but enrolls no embedding."""
    _stub_pipeline(
        monkeypatch,
        VerificationOutput(
            PipelineResult(
                VerificationStatus.REJECTED, None, "LIVENESS_FAILED"
            )
        ),
    )
    _, key = create_mfi_with_key(db_session, usage=0)

    resp = api_client.post(
        VERIFY_URL, data=_data("CLIENT-R"), files=_files(), headers=_auth(key)
    )

    assert resp.status_code == 201
    assert resp.json()["status"] == VerificationStatus.REJECTED.value
    assert resp.json()["reject_reason"] == "LIVENESS_FAILED"
    assert (
        db_session.query(FaceEmbedding).filter_by(client_id="CLIENT-R").count()
        == 0
    )


def test_verify_sets_warning_near_limit(
    api_client: TestClient, db_session: Session, monkeypatch
) -> None:
    """Crossing 80% usage flips the quota_warning flag on."""
    _stub_pipeline(monkeypatch, _verified())
    _, key = create_mfi_with_key(db_session, usage=159)

    resp = api_client.post(
        VERIFY_URL,
        data=_data("CLIENT-002"),
        files=_files(),
        headers=_auth(key),
    )

    assert resp.status_code == 201
    assert resp.json()["quota_warning"] is True


def test_verify_blocked_when_quota_exhausted(
    api_client: TestClient, db_session: Session
) -> None:
    """At the limit the request is blocked with 402 and is not recorded."""
    account, key = create_mfi_with_key(db_session, usage=200)

    resp = api_client.post(
        VERIFY_URL,
        data=_data("CLIENT-003"),
        files=_files(),
        headers=_auth(key),
    )

    assert resp.status_code == 402
    assert resp.json()["error"]["code"] == "QUOTA_EXCEEDED"
    assert account.current_period_usage == 200  # unchanged


def test_verify_requires_authentication(api_client: TestClient) -> None:
    """No API key -> 401 before any quota logic runs."""
    resp = api_client.post(
        VERIFY_URL, data=_data("CLIENT-004"), files=_files()
    )
    assert resp.status_code == 401


def test_verify_persists_all_stage_results(
    api_client: TestClient, db_session: Session, monkeypatch
) -> None:
    """Every stage that ran writes its child record (here a duplicate hit)."""
    output = VerificationOutput(
        result=PipelineResult(VerificationStatus.PENDING, 0.85),
        ocr=OcrResult(
            success=True, full_name="JANE DOE", id_number="ID123",
            date_of_birth=date(1990, 1, 1), occupation="INGENIEUR",
        ),
        liveness=LivenessOutcome(passed=True, score=0.9, method="lbp-svm"),
        face_match=FaceMatchOutcome(
            match_score=0.8, verified=True, threshold=0.4
        ),
        duplicate=DuplicateOutcome(
            is_duplicate=True, similarity=0.9, matched_client_id="CL-9"
        ),
    )
    _stub_pipeline(monkeypatch, output)
    _, key = create_mfi_with_key(db_session, usage=0)

    resp = api_client.post(
        VERIFY_URL, data=_data("CLIENT-S"), files=_files(), headers=_auth(key)
    )

    assert resp.status_code == 201
    vid = uuid.UUID(resp.json()["verification_id"])
    for model in (ExtractedData, LivenessResult, FaceMatchResult,
                  DuplicateFlag):
        assert (
            db_session.query(model).filter_by(verification_id=vid).count()
            == 1
        )
    extracted = (
        db_session.query(ExtractedData).filter_by(verification_id=vid).one()
    )
    assert extracted.full_name == "JANE DOE"
    assert extracted.occupation == "INGENIEUR"


def test_verify_ocr_failure_persists_only_extracted_data(
    api_client: TestClient, db_session: Session, monkeypatch
) -> None:
    """An early OCR reject writes ExtractedData but no later-stage rows."""
    _stub_pipeline(
        monkeypatch,
        VerificationOutput(
            result=PipelineResult(
                VerificationStatus.REJECTED, None, "OCR_FAILED"
            ),
            ocr=OcrResult(success=False),
        ),
    )
    _, key = create_mfi_with_key(db_session, usage=0)

    resp = api_client.post(
        VERIFY_URL, data=_data("CLIENT-OF"), files=_files(), headers=_auth(key)
    )

    vid = uuid.UUID(resp.json()["verification_id"])
    assert (
        db_session.query(ExtractedData).filter_by(verification_id=vid).count()
        == 1
    )
    assert (
        db_session.query(LivenessResult).filter_by(verification_id=vid).count()
        == 0
    )


def test_verify_nic_without_back_is_rejected(
    api_client: TestClient, db_session: Session
) -> None:
    """A NIC upload missing its back image is a 400 validation error."""
    _, key = create_mfi_with_key(db_session, usage=0)

    resp = api_client.post(
        VERIFY_URL,
        data=_data("CLIENT-005", "NIC"),
        files=_files(with_back=False),
        headers=_auth(key),
    )

    assert resp.status_code == 400
