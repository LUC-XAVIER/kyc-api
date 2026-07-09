"""Score-drift monitoring for the face-match model (Evidently).

Tracks whether the distribution of face-match similarity scores has shifted
over time — a proxy for model/population drift (Design doc: detect face-match
drift as the client population changes). A Kolmogorov–Smirnov test compares a
recent window of scores against an earlier reference window; a small p-value
means the distributions differ, i.e. drift. Evidently/pandas are imported
lazily so this module loads without the optional ``ml`` extra.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import FaceMatchResult, Verification

# K-S p-value below this ⇒ the two score distributions differ ⇒ drift.
DRIFT_THRESHOLD = 0.05
# Minimum samples per window for the test to be meaningful.
MIN_SAMPLES = 20

_METHOD = "K-S p_value"


@dataclass(frozen=True)
class DriftOutcome:
    """Result of a drift test between two score samples."""

    method: str
    drift_score: float  # the K-S p-value
    drift_detected: bool


def detect_drift(
    reference: Sequence[float], current: Sequence[float]
) -> DriftOutcome:
    """Run a K-S value-drift test on two score samples via Evidently."""
    import pandas as pd
    from evidently import DataDefinition, Dataset, Report
    from evidently.metrics import ValueDrift

    definition = DataDefinition(numerical_columns=["score"])
    reference_ds = Dataset.from_pandas(
        pd.DataFrame({"score": list(reference)}), data_definition=definition
    )
    current_ds = Dataset.from_pandas(
        pd.DataFrame({"score": list(current)}), data_definition=definition
    )
    snapshot = Report([ValueDrift(column="score")]).run(
        current_data=current_ds, reference_data=reference_ds
    )
    p_value = float(snapshot.dict()["metrics"][0]["value"])
    return DriftOutcome(
        method=_METHOD,
        drift_score=p_value,
        drift_detected=p_value < DRIFT_THRESHOLD,
    )


def face_match_scores(
    db: Session,
    mfi_account_id: uuid.UUID,
    *,
    since: datetime,
    until: datetime,
) -> list[float]:
    """Face-match scores for the MFI's verifications in ``[since, until)``."""
    rows = (
        db.query(FaceMatchResult.match_score)
        .join(Verification, FaceMatchResult.verification_id == Verification.id)
        .filter(
            Verification.mfi_account_id == mfi_account_id,
            Verification.created_at >= since,
            Verification.created_at < until,
        )
        .all()
    )
    return [row[0] for row in rows]
