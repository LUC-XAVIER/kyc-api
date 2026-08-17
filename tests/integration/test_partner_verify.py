"""Integration tests for POST /partner/verify (stateless external API).

The ML pipeline is stubbed (run_verification monkeypatched) so these focus
on the endpoint's own concerns: key auth, the rate limit, the upload cap,
the stateless wiring, and the response shape. No database is touched — the
route persists nothing.
"""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.v1.routes import partner as partner_route
from app.core.config import settings
from app.models.enums import VerificationStatus
from app.pipeline.contracts import (
    FaceMatchOutcome,
    LivenessOutcome,
    OcrResult,
)
from app.pipeline.orchestrator import PipelineResult, VerificationOutput
from app.services.rate_limit import SlidingWindowRateLimiter

PARTNER_URL = "/api/v1/partner/verify"
_KEY = "partner-secret-key-for-tests"


@pytest.fixture
def partner_env(monkeypatch):
    """Enable the partner API with a known key and a permissive limiter."""
    monkeypatch.setattr(settings, "partner_api_key", _KEY)
    monkeypatch.setattr(
        partner_route,
        "_limiter",
        SlidingWindowRateLimiter(1000, window_seconds=60.0),
    )


def _files(*, with_back: bool = True) -> dict:
    image = ("img.png", b"fake-image-bytes", "image/png")
    files = {"id_front": image, "selfie": image}
    if with_back:
        files["id_back"] = image
    return files


def _auth(key: str = _KEY) -> dict[str, str]:
    return {"X-API-Key": key}


def _verified_output() -> VerificationOutput:
    return VerificationOutput(
        result=PipelineResult(VerificationStatus.VERIFIED, 0.9),
        embedding=np.zeros(512, dtype=np.float32),
        ocr=OcrResult(
            success=True,
            full_name="JANE DOE",
            id_number="ID123",
            field_confidences={"full_name": 0.98},
        ),
        liveness=LivenessOutcome(passed=True, score=0.95, method="fasnet"),
        face_match=FaceMatchOutcome(
            match_score=0.82, verified=True, threshold=0.6
        ),
    )


def _stub_pipeline(monkeypatch, output: VerificationOutput) -> dict:
    """Patch the pipeline; return a dict capturing its call arguments."""
    captured: dict = {}

    def _run(data, *, duplicate_store):
        captured["input"] = data
        captured["store"] = duplicate_store
        return output

    monkeypatch.setattr(partner_route, "run_verification", _run)
    return captured


def test_returns_full_per_stage_result(
    client: TestClient, partner_env, monkeypatch
) -> None:
    """A verified run returns the verdict plus every stage that ran."""
    _stub_pipeline(monkeypatch, _verified_output())

    resp = client.post(
        PARTNER_URL,
        data={"document_type": "NIC", "reference": "REF-1"},
        files=_files(),
        headers=_auth(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == VerificationStatus.VERIFIED.value
    assert body["confidence_score"] == 0.9
    assert body["reference"] == "REF-1"
    assert body["extracted_data"]["full_name"] == "JANE DOE"
    assert body["liveness"]["score"] == 0.95
    assert body["face_match"]["match_score"] == 0.82
    # Stateless: nothing is stored, so no record id comes back.
    assert "verification_id" not in body


def test_is_stateless_and_skips_duplicate_search(
    client: TestClient, partner_env, monkeypatch
) -> None:
    """The pipeline runs with the no-op store; duplicates never sought."""
    captured = _stub_pipeline(monkeypatch, _verified_output())

    resp = client.post(
        PARTNER_URL,
        data={"document_type": "NIC"},
        files=_files(),
        headers=_auth(),
    )

    assert resp.status_code == 200
    assert isinstance(
        captured["store"], partner_route._StatelessDuplicateStore
    )
    # An empty index reports every face as unique.
    index = captured["store"].build_index(None, exclude_client_id="x")
    outcome = index.search(np.zeros(512, dtype=np.float32))
    assert outcome.is_duplicate is False


def test_rejected_result_has_null_later_stages(
    client: TestClient, partner_env, monkeypatch
) -> None:
    """An early liveness reject returns REJECTED with no face-match block."""
    _stub_pipeline(
        monkeypatch,
        VerificationOutput(
            result=PipelineResult(
                VerificationStatus.REJECTED, 0.1, "LIVENESS_FAILED"
            ),
            liveness=LivenessOutcome(passed=False, score=0.1, method="fasnet"),
        ),
    )

    resp = client.post(
        PARTNER_URL,
        data={"document_type": "NIC"},
        files=_files(),
        headers=_auth(),
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == VerificationStatus.REJECTED.value
    assert body["reject_reason"] == "LIVENESS_FAILED"
    assert body["face_match"] is None
    assert body["extracted_data"] is None


def test_missing_key_is_unauthorized(
    client: TestClient, partner_env
) -> None:
    """No API key -> 401, pipeline never runs."""
    resp = client.post(
        PARTNER_URL, data={"document_type": "NIC"}, files=_files()
    )
    assert resp.status_code == 401


def test_wrong_key_is_unauthorized(
    client: TestClient, partner_env
) -> None:
    """A key that doesn't match the configured secret -> 401."""
    resp = client.post(
        PARTNER_URL,
        data={"document_type": "NIC"},
        files=_files(),
        headers=_auth("not-the-key"),
    )
    assert resp.status_code == 401


def test_disabled_when_unconfigured(
    client: TestClient, monkeypatch
) -> None:
    """With no partner key set, the endpoint is closed even with a header."""
    monkeypatch.setattr(settings, "partner_api_key", "")
    resp = client.post(
        PARTNER_URL,
        data={"document_type": "NIC"},
        files=_files(),
        headers=_auth("anything"),
    )
    assert resp.status_code == 401


def test_nic_without_back_is_rejected(
    client: TestClient, partner_env
) -> None:
    """A NIC missing its back image is a 400 before the pipeline runs."""
    resp = client.post(
        PARTNER_URL,
        data={"document_type": "NIC"},
        files=_files(with_back=False),
        headers=_auth(),
    )
    assert resp.status_code == 400


def test_oversized_image_is_rejected(
    client: TestClient, partner_env, monkeypatch
) -> None:
    """An upload over the size cap -> 413 before the pipeline runs."""
    monkeypatch.setattr(settings, "max_upload_bytes", 8)
    big = ("img.png", b"way-too-many-bytes", "image/png")

    resp = client.post(
        PARTNER_URL,
        data={"document_type": "NIC"},
        files={"id_front": big, "selfie": big, "id_back": big},
        headers=_auth(),
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_rate_limit_returns_429(
    client: TestClient, monkeypatch
) -> None:
    """Once over the per-key limit, further calls get 429."""
    monkeypatch.setattr(settings, "partner_api_key", _KEY)
    monkeypatch.setattr(
        partner_route,
        "_limiter",
        SlidingWindowRateLimiter(1, window_seconds=60.0),
    )
    _stub_pipeline(monkeypatch, _verified_output())

    first = client.post(
        PARTNER_URL,
        data={"document_type": "NIC"},
        files=_files(),
        headers=_auth(),
    )
    second = client.post(
        PARTNER_URL,
        data={"document_type": "NIC"},
        files=_files(),
        headers=_auth(),
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["error"]["code"] == "RATE_LIMITED"
