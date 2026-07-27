"""Cross-tenant model-monitoring aggregates for the admin dashboard.

Every figure here is computed from data the pipeline already stores
(``face_match_results``, ``liveness_results``, ``extracted_data`` OCR
confidences, ``face_embeddings``, ``duplicate_flags``). Nothing is fabricated
— metrics we don't have ground truth for (FAR/FRR, attack types) are simply
not produced.
"""

from sqlalchemy import Integer, cast, func
from sqlalchemy.orm import Session

from app.models import (
    DuplicateFlag,
    ExtractedData,
    FaceEmbedding,
    FaceMatchResult,
    LivenessResult,
    MfiAccount,
    Verification,
)
from app.models.enums import DuplicateResolution
from app.schemas.admin import (
    AntiSpoofReport,
    DuplicateReport,
    FaceMatchingReport,
    ModelHealthReport,
    OcrFieldAccuracy,
    OcrReport,
    PerMfiScore,
    ScoreBucket,
)

# Histogram resolution for the 0.0–1.0 score charts.
BINS = 10


def _r(value: float | None, digits: int = 3) -> float | None:
    """Round a nullable aggregate for display."""
    return round(float(value), digits) if value is not None else None


def _histogram(db: Session, score_col) -> list[ScoreBucket]:
    """Bucket a 0..1 score column into ``BINS`` bars, zero-filled."""
    bucket = func.least(cast(func.floor(score_col * BINS), Integer), BINS - 1)
    rows = (
        db.query(bucket, func.count())
        .filter(score_col.isnot(None))
        .group_by(bucket)
        .all()
    )
    counts = {int(b): c for b, c in rows}
    return [
        ScoreBucket(label=f"{i / BINS:.1f}", count=counts.get(i, 0))
        for i in range(BINS)
    ]


def _face_matching(db: Session) -> FaceMatchingReport:
    fm = FaceMatchResult
    evaluated = db.query(func.count(fm.id)).scalar() or 0
    avg_score = db.query(func.avg(fm.match_score)).scalar()
    verified_rate = db.query(func.avg(cast(fm.verified, Integer))).scalar()
    # The operative threshold: the one most rows were scored against.
    threshold_row = (
        db.query(fm.threshold, func.count())
        .group_by(fm.threshold)
        .order_by(func.count().desc())
        .first()
    )
    per_mfi = [
        PerMfiScore(
            name=name,
            evaluated=count,
            avg_score=_r(avg),
            verified_rate=_r(vrate),
        )
        for name, count, avg, vrate in (
            db.query(
                MfiAccount.name,
                func.count(fm.id),
                func.avg(fm.match_score),
                func.avg(cast(fm.verified, Integer)),
            )
            .join(Verification, fm.verification_id == Verification.id)
            .join(MfiAccount, Verification.mfi_account_id == MfiAccount.id)
            .group_by(MfiAccount.name)
            .order_by(func.avg(fm.match_score).asc())  # weakest first
            .all()
        )
    ]
    return FaceMatchingReport(
        evaluated=evaluated,
        avg_score=_r(avg_score),
        threshold=_r(threshold_row[0]) if threshold_row else None,
        verified_rate=_r(verified_rate),
        distribution=_histogram(db, fm.match_score),
        per_mfi=per_mfi,
    )


def _anti_spoofing(db: Session) -> AntiSpoofReport:
    lr = LivenessResult
    evaluated = db.query(func.count(lr.id)).scalar() or 0
    avg_score = db.query(func.avg(lr.anti_spoof_score)).scalar()
    pass_rate = db.query(func.avg(cast(lr.passed, Integer))).scalar()
    spoof_flagged = (
        db.query(func.count(lr.id)).filter(lr.passed.is_(False)).scalar()
        or 0
    )
    return AntiSpoofReport(
        evaluated=evaluated,
        avg_score=_r(avg_score),
        pass_rate=_r(pass_rate),
        spoof_flagged=spoof_flagged,
        distribution=_histogram(db, lr.anti_spoof_score),
    )


def _ocr(db: Session) -> OcrReport:
    rows = (
        db.query(ExtractedData.field_confidences)
        .filter(ExtractedData.field_confidences.isnot(None))
        .all()
    )
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for (confidences,) in rows:
        if not isinstance(confidences, dict):
            continue
        for field, value in confidences.items():
            if isinstance(value, int | float):
                sums[field] = sums.get(field, 0.0) + value
                counts[field] = counts.get(field, 0) + 1
    per_field = [
        OcrFieldAccuracy(
            field=field,
            avg_confidence=round(sums[field] / counts[field], 3),
            samples=counts[field],
        )
        for field in sorted(sums)
    ]
    total = sum(counts.values())
    overall = round(sum(sums.values()) / total, 3) if total else None
    return OcrReport(
        evaluated=len(rows), avg_confidence=overall, per_field=per_field
    )


def _duplicate(db: Session) -> DuplicateReport:
    res_counts = {
        r: c
        for r, c in db.query(
            DuplicateFlag.resolution, func.count()
        ).group_by(DuplicateFlag.resolution).all()
    }
    return DuplicateReport(
        index_size=db.query(func.count(FaceEmbedding.id)).scalar() or 0,
        flags=db.query(func.count(DuplicateFlag.id)).scalar() or 0,
        avg_similarity=_r(
            db.query(func.avg(DuplicateFlag.similarity_score)).scalar()
        ),
        confirmed=res_counts.get(DuplicateResolution.CONFIRMED, 0),
        dismissed=res_counts.get(DuplicateResolution.DISMISSED, 0),
        pending=res_counts.get(DuplicateResolution.PENDING, 0),
    )


def model_health(db: Session) -> ModelHealthReport:
    """Aggregate every model's stored results into one monitoring payload."""
    return ModelHealthReport(
        face_matching=_face_matching(db),
        anti_spoofing=_anti_spoofing(db),
        ocr=_ocr(db),
        duplicate=_duplicate(db),
    )
