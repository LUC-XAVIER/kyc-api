"""Response schema for drift monitoring."""

from pydantic import BaseModel


class DriftReport(BaseModel):
    """Face-match score drift over a recent window vs. an earlier one."""

    metric: str = "face_match_score"
    method: str | None
    drift_score: float | None
    drift_detected: bool
    reference_size: int
    current_size: int
    sufficient_data: bool
