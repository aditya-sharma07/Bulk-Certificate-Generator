from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from app.schemas import CertificateDetails, RecipientInput


def _fitted_font_size(text: str, font: str, preferred: int, max_width: float) -> int:
    size = preferred
    while size > 18 and stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def generate_certificate(
    output_path: Path,
    certificate: CertificateDetails,
    recipient: RecipientInput,
    certificate_id: str,
) -> None:
    """Render one certificate to a temporary file and atomically publish it."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(f".{uuid4().hex}.tmp")
    width, height = landscape(A4)

    try:
        pdf = Canvas(str(temporary_path), pagesize=(width, height))
        pdf.setTitle(f"{certificate.title} - {recipient.name}")
        pdf.setAuthor(certificate.issuer)

        navy = HexColor("#17324D")
        gold = HexColor("#C69C3C")
        muted = HexColor("#52616B")

        pdf.setFillColor(HexColor("#FAF8F2"))
        pdf.rect(0, 0, width, height, fill=1, stroke=0)
        pdf.setStrokeColor(navy)
        pdf.setLineWidth(5)
        pdf.rect(25, 25, width - 50, height - 50, fill=0, stroke=1)
        pdf.setStrokeColor(gold)
        pdf.setLineWidth(1.5)
        pdf.rect(36, 36, width - 72, height - 72, fill=0, stroke=1)

        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", 30)
        pdf.drawCentredString(width / 2, height - 110, certificate.title.upper())

        pdf.setFillColor(muted)
        pdf.setFont("Helvetica", 15)
        pdf.drawCentredString(width / 2, height - 160, "This certificate is presented to")

        name_size = _fitted_font_size(
            recipient.name, "Helvetica-Bold", 34, width - 150
        )
        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", name_size)
        pdf.drawCentredString(width / 2, height - 225, recipient.name)

        pdf.setStrokeColor(gold)
        pdf.setLineWidth(1)
        pdf.line(150, height - 240, width - 150, height - 240)

        pdf.setFillColor(muted)
        pdf.setFont("Helvetica", 14)
        pdf.drawCentredString(width / 2, height - 285, "for successfully completing")

        course_size = _fitted_font_size(
            certificate.course, "Helvetica-Bold", 23, width - 160
        )
        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", course_size)
        pdf.drawCentredString(width / 2, height - 330, certificate.course)

        pdf.setFillColor(muted)
        pdf.setFont("Helvetica", 12)
        pdf.drawCentredString(
            width / 2,
            125,
            f"Issued by {certificate.issuer} on {certificate.issue_date.isoformat()}",
        )
        pdf.setFont("Helvetica", 8)
        pdf.drawCentredString(width / 2, 70, f"Certificate ID: {certificate_id}")

        pdf.showPage()
        pdf.save()
        os.replace(temporary_path, output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

