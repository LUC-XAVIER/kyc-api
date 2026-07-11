"""Render a :class:`ComplianceReport` to a COBAC-ready PDF (ReportLab).

Lays out the Openxtech-branded compliance report from the design mockup:
a header with the generation stamp and report id, four KPI cards (total /
verified / pending / rejected), the per-verification detail table, and a
confidential footer with page numbers.
"""

from datetime import UTC, datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models import ComplianceReport
from app.models.enums import VerificationStatus
from app.services.reporting import ReportRow

_RED = colors.HexColor("#CE2835")
_GREEN = colors.HexColor("#1D9E75")
_ORANGE = colors.HexColor("#E67E22")
_NAVY = colors.HexColor("#212529")
_LIGHT = colors.HexColor("#F3F5F8")
_GREY = colors.HexColor("#6B7280")
_BORDER = colors.HexColor("#E5E7EB")

_STATUS_COLOR = {
    VerificationStatus.VERIFIED.value: _GREEN,
    VerificationStatus.APPROVED.value: _GREEN,
    VerificationStatus.PENDING.value: _ORANGE,
    VerificationStatus.REJECTED.value: _RED,
}

_MARGIN = 18 * mm
_COL_WIDTHS = [32 * mm, 22 * mm, 40 * mm, 46 * mm, 26 * mm]

_TITLE = ParagraphStyle(
    "title", fontName="Helvetica-Bold", fontSize=17, textColor=_NAVY,
    leading=21, spaceAfter=6,
)
_SUBTITLE = ParagraphStyle(
    "subtitle", fontName="Helvetica", fontSize=9, textColor=_GREY,
    spaceAfter=6,
)
_CELL = ParagraphStyle(
    "cell", fontName="Helvetica", fontSize=8.5, textColor=_NAVY, leading=11,
)
_HEAD = ParagraphStyle(
    "head", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white,
    leading=11,
)


class _NumberedCanvas(canvas.Canvas):
    """Canvas that defers page rendering so it can stamp "Page X of Y"."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._saved_states: list[dict] = []

    def showPage(self) -> None:  # noqa: N802  (ReportLab API override)
        """Buffer the page instead of emitting it immediately."""
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        """Emit every buffered page, now that the total is known."""
        total = len(self._saved_states)
        for state in self._saved_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_footer(self, total: int) -> None:
        self.setFont("Helvetica", 8)
        self.setFillColor(_GREY)
        self.drawString(
            _MARGIN, 12 * mm,
            "Confidential — for COBAC audit purposes only",
        )
        self.drawRightString(
            A4[0] - _MARGIN, 12 * mm,
            f"Page {self._pageNumber} of {total}",
        )


def _report_id(report: ComplianceReport) -> str:
    """Build the human-readable report id shown on the document."""
    stamp = report.generated_at or datetime.now(UTC)
    return f"RPT-{stamp:%Y%m%d}-{str(report.id)[:4].upper()}"


def _header(report: ComplianceReport) -> Table:
    stamp = report.generated_at or datetime.now(UTC)
    brand = ParagraphStyle(
        "brand", fontName="Helvetica-Bold", fontSize=13, textColor=_RED,
    )
    meta = ParagraphStyle(
        "meta", fontName="Helvetica", fontSize=8, textColor=_GREY,
        alignment=2, leading=11,
    )
    table = Table(
        [[
            Paragraph("OPENXTECH", brand),
            Paragraph(
                f"Generated: {stamp:%d %b %Y, %H:%M}<br/>"
                f"Report ID: {_report_id(report)}",
                meta,
            ),
        ]],
        colWidths=[sum(_COL_WIDTHS) / 2] * 2,
    )
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1, _NAVY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def _kpi_cards(report: ComplianceReport) -> Table:
    breakdown = report.status_breakdown or {}
    verified = breakdown.get(
        VerificationStatus.VERIFIED.value, 0
    ) + breakdown.get(VerificationStatus.APPROVED.value, 0)
    cards = [
        ("Total verifications", report.total_verifications, _NAVY),
        ("Verified", verified, _GREEN),
        ("Pending", breakdown.get(VerificationStatus.PENDING.value, 0),
         _ORANGE),
        ("Rejected", breakdown.get(VerificationStatus.REJECTED.value, 0),
         _RED),
    ]
    label_style = ParagraphStyle(
        "lbl", fontName="Helvetica", fontSize=8, textColor=_GREY,
    )
    pad = TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ])
    # Each card is its own mini-table so the number sits above the label.
    cells = []
    for label, value, color in cards:
        num_style = ParagraphStyle(
            "num", fontName="Helvetica-Bold", fontSize=15, textColor=color,
        )
        cells.append(Table(
            [[Paragraph(str(value), num_style)],
             [Paragraph(label, label_style)]],
            style=pad,
        ))
    table = Table([cells], colWidths=[sum(_COL_WIDTHS) / 4] * 4)
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, _BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, _BORDER),
        ("BACKGROUND", (0, 0), (-1, -1), _LIGHT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table


def _detail_table(rows: list[ReportRow]) -> Table:
    header = [Paragraph(h, _HEAD) for h in
              ("CLIENT ID", "DATE", "BRANCH", "AGENT", "STATUS")]
    body = [header]
    for r in rows:
        status_style = ParagraphStyle(
            "st", parent=_CELL, textColor=_STATUS_COLOR.get(r.status, _NAVY),
            fontName="Helvetica-Bold",
        )
        body.append([
            Paragraph(r.client_id, _CELL),
            Paragraph(r.date.strftime("%d %b %Y"), _CELL),
            Paragraph(r.branch, _CELL),
            Paragraph(r.agent, _CELL),
            Paragraph(r.status, status_style),
        ])
    table = Table(body, colWidths=_COL_WIDTHS, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, _BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return table


def render_report_pdf(
    report: ComplianceReport,
    rows: list[ReportRow],
    *,
    mfi_name: str,
) -> bytes:
    """Render ``report`` and its verification ``rows`` to PDF bytes.

    Args:
        report: The persisted compliance report to render.
        rows: The per-verification detail lines (see
            :func:`app.services.reporting.report_rows`).
        mfi_name: The MFI's display name for the subtitle.

    Returns:
        The complete PDF document as bytes.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=_MARGIN, rightMargin=_MARGIN,
        topMargin=_MARGIN, bottomMargin=20 * mm,
        title="KYC Compliance Report",
    )
    subtitle = (
        f"{mfi_name} · Period: {report.period_start:%d %b %Y} – "
        f"{report.period_end:%d %b %Y} · All branches"
    )
    story = [
        _header(report),
        Spacer(1, 8),
        Paragraph("KYC Compliance Report", _TITLE),
        Paragraph(subtitle, _SUBTITLE),
        Spacer(1, 6),
        _kpi_cards(report),
        Spacer(1, 12),
        _detail_table(rows),
    ]
    doc.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()
