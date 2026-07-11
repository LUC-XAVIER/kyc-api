"""Unit tests for the compliance-report PDF renderer (no DB)."""

import uuid
from datetime import UTC, date, datetime

from app.models import ComplianceReport
from app.services.report_pdf import render_report_pdf
from app.services.reporting import ReportRow


def _report() -> ComplianceReport:
    return ComplianceReport(
        id=uuid.uuid4(),
        mfi_account_id=uuid.uuid4(),
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 17),
        total_verifications=3,
        status_breakdown={"VERIFIED": 2, "PENDING": 1},
        generated_at=datetime(2026, 6, 17, 14, 32, tzinfo=UTC),
    )


def test_render_produces_pdf_bytes() -> None:
    """A populated report renders to a non-trivial PDF document."""
    rows = [
        ReportRow("CLT-1", date(2026, 6, 17), "Mvog-Ada", "J. Mbarga",
                  "VERIFIED"),
        ReportRow("CLT-2", date(2026, 6, 16), "Biyem-Assi", "P. Onana",
                  "PENDING"),
    ]
    pdf = render_report_pdf(_report(), rows, mfi_name="CamFinance")
    assert pdf[:5] == b"%PDF-"
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 1000


def test_render_handles_empty_rows_and_missing_stamp() -> None:
    """No rows and an unflushed report (no generated_at) still render."""
    report = _report()
    report.generated_at = None
    pdf = render_report_pdf(report, [], mfi_name="CamFinance")
    assert pdf[:5] == b"%PDF-"
