from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from app.schemas import CertificateInfo, RecipientData


def _draw_centered_paragraph(
    pdf: canvas.Canvas,
    text: str,
    *,
    y: float,
    width: float,
    style: ParagraphStyle,
) -> None:
    paragraph = Paragraph(escape(text), style)
    _, height = paragraph.wrap(width, 160)
    paragraph.drawOn(pdf, (landscape(A4)[0] - width) / 2, y - height)


def generate_certificate(
    output_path: Path,
    recipient: RecipientData,
    certificate: CertificateInfo,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    page_width, page_height = landscape(A4)
    pdf = canvas.Canvas(str(output_path), pagesize=(page_width, page_height))

    pdf.setFillColor(colors.HexColor("#17365D"))
    pdf.setStrokeColor(colors.HexColor("#B08D57"))
    pdf.setLineWidth(3)
    pdf.rect(28, 28, page_width - 56, page_height - 56)
    pdf.setLineWidth(1)
    pdf.rect(38, 38, page_width - 76, page_height - 76)

    _draw_centered_paragraph(
        pdf,
        "CERTIFICATE",
        y=page_height - 95,
        width=page_width - 130,
        style=ParagraphStyle(
            "CertificateHeading",
            fontName="Helvetica-Bold",
            fontSize=28,
            leading=34,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#17365D"),
        ),
    )
    _draw_centered_paragraph(
        pdf,
        certificate.certificate_title,
        y=page_height - 145,
        width=page_width - 150,
        style=ParagraphStyle(
            "CertificateTitle",
            fontName="Helvetica",
            fontSize=17,
            leading=22,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#333333"),
        ),
    )
    pdf.setFont("Helvetica", 13)
    pdf.setFillColor(colors.HexColor("#333333"))
    pdf.drawCentredString(page_width / 2, page_height - 205, "This certificate is presented to")

    _draw_centered_paragraph(
        pdf,
        recipient.name,
        y=page_height - 235,
        width=page_width - 110,
        style=ParagraphStyle(
            "RecipientName",
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=31,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#17365D"),
        ),
    )
    _draw_centered_paragraph(
        pdf,
        f"for participation in {certificate.event_name}",
        y=page_height - 290,
        width=page_width - 130,
        style=ParagraphStyle(
            "EventName",
            fontName="Helvetica",
            fontSize=15,
            leading=20,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#333333"),
        ),
    )

    _draw_centered_paragraph(
        pdf,
        f"Issued {certificate.issue_date.strftime('%B %d, %Y')} by {certificate.issuer}",
        y=128,
        width=page_width - 150,
        style=ParagraphStyle(
            "Issuer",
            fontName="Helvetica",
            fontSize=11,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#333333"),
        ),
    )
    if recipient.email:
        _draw_centered_paragraph(
            pdf,
            recipient.email,
            y=82,
            width=page_width - 150,
            style=ParagraphStyle(
                "RecipientEmail",
                fontName="Helvetica",
                fontSize=9,
                leading=12,
                alignment=TA_CENTER,
                textColor=colors.HexColor("#555555"),
            ),
        )

    pdf.save()
