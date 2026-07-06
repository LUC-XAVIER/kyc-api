"""Unit tests for the pipeline orchestrator's composition and early exit.

Every stage is stubbed, so these run without the ML extra and focus purely
on ordering, short-circuiting, and the final verdict/enrollment.
"""

import uuid
from datetime import date

import pytest

from app.models.enums import DocumentType, VerificationStatus
from app.pipeline import orchestrator
from app.pipeline.contracts import (
    DuplicateOutcome,
    FaceMatchOutcome,
    LivenessOutcome,
    OcrResult,
    PipelineInput,
    RejectReason,
)

_EMBEDDING = [1.0, 0.0]


class _FakeStore:
    """In-memory DuplicateStore recording enrollments."""

    def __init__(self, duplicate: DuplicateOutcome) -> None:
        self._duplicate = duplicate
        self.added: list[tuple] = []
        self.built_for: list[str] = []

    def build_index(self, mfi_account_id, *, exclude_client_id):
        self.built_for.append(exclude_client_id)
        outcome = self._duplicate

        class _Index:
            def search(self, embedding, **_kwargs):
                return outcome

        return _Index()

    def add_embedding(self, mfi_account_id, client_id, embedding):
        self.added.append((client_id, embedding))


def _boom(*_args, **_kwargs):
    """Stand-in for a stage that must not run; fails loudly if called."""
    raise AssertionError("this stage should have been skipped")


def _input() -> PipelineInput:
    return PipelineInput(
        client_id="CL-1",
        mfi_account_id=uuid.uuid4(),
        document_type=DocumentType.NIC,
        id_front_image=b"front",
        selfie_image=b"selfie",
        id_back_image=b"back",
    )


@pytest.fixture
def wire(monkeypatch):
    """Patch every stage with canned outputs; return the fake store."""

    def _wire(
        *,
        ocr: OcrResult,
        liveness: LivenessOutcome | None = None,
        face: FaceMatchOutcome | None = None,
        duplicate: DuplicateOutcome | None = None,
    ) -> _FakeStore:
        from types import SimpleNamespace

        monkeypatch.setattr(orchestrator, "preprocess_image", lambda b: b)
        monkeypatch.setattr(
            orchestrator,
            "crop_nic_zones",
            lambda img: SimpleNamespace(text_zone="text", photo_zone="photo"),
        )
        monkeypatch.setattr(
            orchestrator, "ocr_extract", lambda *a, **k: ocr
        )
        monkeypatch.setattr(
            orchestrator,
            "check_liveness",
            (lambda s: liveness) if liveness is not None else _boom,
        )
        monkeypatch.setattr(
            orchestrator, "represent_face",
            (lambda img: _EMBEDDING) if face is not None else _boom,
        )
        monkeypatch.setattr(
            orchestrator, "match_embeddings",
            (lambda a, b: face) if face is not None else _boom,
        )
        return _FakeStore(
            duplicate
            or DuplicateOutcome(is_duplicate=False, similarity=0.0)
        )

    return _wire


@pytest.mark.parametrize(
    ("document_type", "id_back", "expected_region"),
    [
        (DocumentType.NIC, b"back", "TEXTZONE"),  # cropped text zone
        (DocumentType.PASSPORT, None, b"FRONT"),  # full page (MRZ spans it)
    ],
)
def test_ocr_region_depends_on_document_type(
    monkeypatch, document_type, id_back, expected_region
) -> None:
    """A NIC OCRs the text zone; a passport OCRs the whole front page."""
    from types import SimpleNamespace

    captured = {}
    monkeypatch.setattr(orchestrator, "preprocess_image", lambda b: b)
    monkeypatch.setattr(
        orchestrator,
        "crop_nic_zones",
        lambda img: SimpleNamespace(text_zone="TEXTZONE", photo_zone="p"),
    )

    def _capture_ocr(region, doc_type, *, back_image=None):
        captured["region"] = region
        return OcrResult(success=False)  # short-circuit after OCR

    monkeypatch.setattr(orchestrator, "ocr_extract", _capture_ocr)
    store = _FakeStore(DuplicateOutcome(is_duplicate=False, similarity=0.0))
    data = PipelineInput(
        client_id="CL-1",
        mfi_account_id=uuid.uuid4(),
        document_type=document_type,
        id_front_image=b"FRONT",
        selfie_image=b"selfie",
        id_back_image=id_back,
    )

    orchestrator.run_verification(data, duplicate_store=store)

    assert captured["region"] == expected_region


def test_ocr_failure_rejects_before_any_face_work(wire) -> None:
    """Unreadable OCR rejects immediately; later stages never run."""
    store = wire(ocr=OcrResult(success=False))  # liveness/face -> _boom

    result = orchestrator.run_verification(_input(), duplicate_store=store)

    assert result.status is VerificationStatus.REJECTED
    assert result.reject_reason == RejectReason.OCR_FAILED


def test_expired_id_is_rejected(wire) -> None:
    """A past expiry date rejects with ID_EXPIRED."""
    store = wire(
        ocr=OcrResult(success=True, expiry_date=date(2000, 1, 1))
    )

    result = orchestrator.run_verification(_input(), duplicate_store=store)

    assert result.status is VerificationStatus.REJECTED
    assert result.reject_reason == RejectReason.ID_EXPIRED


def test_failed_liveness_skips_face_and_duplicate(wire) -> None:
    """A liveness failure short-circuits the face stages."""
    store = wire(
        ocr=OcrResult(success=True, expiry_date=date(2999, 1, 1)),
        liveness=LivenessOutcome(passed=False, score=0.1, method="m"),
        # face is None -> represent_face/match_embeddings are _boom
    )

    result = orchestrator.run_verification(_input(), duplicate_store=store)

    assert result.status is VerificationStatus.REJECTED
    assert result.reject_reason == RejectReason.LIVENESS_FAILED
    assert store.built_for == []  # duplicate search skipped


def test_face_mismatch_skips_duplicate(wire) -> None:
    """A face mismatch rejects without a duplicate search."""
    store = wire(
        ocr=OcrResult(success=True),
        liveness=LivenessOutcome(passed=True, score=0.9, method="m"),
        face=FaceMatchOutcome(match_score=0.1, verified=False, threshold=0.4),
    )

    result = orchestrator.run_verification(_input(), duplicate_store=store)

    assert result.status is VerificationStatus.REJECTED
    assert result.reject_reason == RejectReason.FACE_MISMATCH
    assert store.built_for == []
    assert store.added == []


def test_duplicate_goes_to_pending_without_enrollment(wire) -> None:
    """A duplicate hit yields PENDING and does not enroll the embedding."""
    store = wire(
        ocr=OcrResult(success=True),
        liveness=LivenessOutcome(passed=True, score=0.9, method="m"),
        face=FaceMatchOutcome(match_score=0.8, verified=True, threshold=0.4),
        duplicate=DuplicateOutcome(
            is_duplicate=True, similarity=0.9, matched_client_id="CL-9"
        ),
    )

    result = orchestrator.run_verification(_input(), duplicate_store=store)

    assert result.status is VerificationStatus.PENDING
    assert store.built_for == ["CL-1"]  # searched, excluding self
    assert store.added == []  # not enrolled on PENDING


def test_clean_pass_verifies_and_enrolls(wire) -> None:
    """A clean run verifies and enrolls the selfie embedding."""
    store = wire(
        ocr=OcrResult(success=True),
        liveness=LivenessOutcome(passed=True, score=0.9, method="m"),
        face=FaceMatchOutcome(match_score=0.8, verified=True, threshold=0.4),
        duplicate=DuplicateOutcome(is_duplicate=False, similarity=0.2),
    )

    result = orchestrator.run_verification(_input(), duplicate_store=store)

    assert result.status is VerificationStatus.VERIFIED
    assert result.confidence is not None
    assert store.added == [("CL-1", _EMBEDDING)]
