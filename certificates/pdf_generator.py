import tempfile
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.conf import settings
from .models import Certificate


# Velttech Brand Colors
GOLD = '#F4C318'
ORANGE = '#F28A1A'
GREEN = '#7AC943'
TECH_BLUE = '#9CCED9'
DARK = '#0F172A'


class CertificatePDFGenerator:
    """Generate professional certificate PDFs"""

    def __init__(self, certificate: Certificate):
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import inch

        self.certificate = certificate
        self.page_width, self.page_height = letter
        self.margin = 0.5 * inch

    def generate_qr_code(self, data: str):
        """Generate QR code image"""
        import qrcode

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        return qr.make_image(fill_color="black", back_color="white")

    def generate_pdf(self) -> bytes:
        """Generate certificate PDF and return bytes"""
        from reportlab.lib.colors import HexColor
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas

        buffer = BytesIO()
        page_width, page_height = landscape(letter)
        pdf = canvas.Canvas(buffer, pagesize=(page_width, page_height))
        dark = HexColor(DARK)
        gold = HexColor(GOLD)
        orange = HexColor(ORANGE)
        tech_blue = HexColor(TECH_BLUE)

        pdf.setStrokeColor(gold)
        pdf.setLineWidth(5)
        pdf.rect(0.35 * inch, 0.35 * inch, page_width - 0.7 * inch, page_height - 0.7 * inch)
        pdf.setStrokeColor(orange)
        pdf.setLineWidth(1.5)
        pdf.rect(0.55 * inch, 0.55 * inch, page_width - 1.1 * inch, page_height - 1.1 * inch)

        logo_path = Path(settings.BASE_DIR).parent / 'frontend' / 'public' / 'images' / 'velttech-logo.png'
        if logo_path.exists():
            pdf.drawImage(
                str(logo_path),
                (page_width - 1.8 * inch) / 2,
                page_height - 1.25 * inch,
                width=1.8 * inch,
                height=0.78 * inch,
                preserveAspectRatio=True,
                mask='auto',
            )

        certificate_title = f"Certificate of {self.certificate.get_certificate_type_display()}"
        pdf.setFillColor(gold)
        pdf.setFont('Helvetica-Bold', 30)
        pdf.drawCentredString(page_width / 2, page_height - 1.72 * inch, certificate_title)

        pdf.setFillColor(dark)
        pdf.setFont('Helvetica', 13)
        pdf.drawCentredString(page_width / 2, page_height - 2.15 * inch, 'This certificate is proudly presented to')

        pdf.setFillColor(orange)
        pdf.setFont('Helvetica-Bold', 28)
        pdf.drawCentredString(page_width / 2, page_height - 2.65 * inch, self._get_student_name())

        pdf.setFillColor(dark)
        pdf.setFont('Helvetica', 13)
        pdf.drawCentredString(page_width / 2, page_height - 3.05 * inch, 'for successfully completing')
        pdf.setFont('Helvetica-Bold', 18)
        pdf.drawCentredString(page_width / 2, page_height - 3.42 * inch, self.certificate.course.title)

        issue_date = self.certificate.issue_date
        if not issue_date and self.certificate.issued_at:
            issue_date = self.certificate.issued_at.date()
        verification_url = f"https://portal.velttech.org/verify/{self.certificate.certificate_number}/"
        detail_rows = [
            ('Completion Date', self.certificate.completion_date.strftime('%B %d, %Y')),
            ('Final Grade', self.certificate.final_grade or 'Not recorded'),
            ('Final Score', self._percentage_text(self.certificate.final_score)),
            ('Attendance', self._percentage_text(self.certificate.attendance_percentage)),
            ('Certificate Number', self.certificate.certificate_number),
            ('Issue Date', issue_date.strftime('%B %d, %Y') if issue_date else 'Not recorded'),
        ]

        left_x = 1.35 * inch
        right_x = 5.65 * inch
        start_y = page_height - 4.08 * inch
        row_gap = 0.32 * inch
        for index, (label, value) in enumerate(detail_rows):
            x = left_x if index < 3 else right_x
            y = start_y - (index % 3) * row_gap
            pdf.setFillColor(dark)
            pdf.setFont('Helvetica-Bold', 10)
            pdf.drawString(x, y, f'{label}:')
            pdf.setFont('Helvetica', 10)
            pdf.drawString(x + 1.35 * inch, y, str(value))

        pdf.setFillColor(tech_blue)
        pdf.setFont('Helvetica-Oblique', 9)
        pdf.drawCentredString(page_width / 2, 1.72 * inch, f'Verify online: {verification_url}')

        pdf.setStrokeColor(dark)
        pdf.setLineWidth(1)
        pdf.line(1.4 * inch, 1.15 * inch, 3.45 * inch, 1.15 * inch)
        pdf.line(page_width - 3.45 * inch, 1.15 * inch, page_width - 1.4 * inch, 1.15 * inch)
        pdf.setFillColor(dark)
        pdf.setFont('Helvetica-Bold', 10)
        pdf.drawCentredString(2.425 * inch, 0.93 * inch, 'Director Signature')
        pdf.drawCentredString(page_width - 2.425 * inch, 0.93 * inch, 'Instructor Signature')

        pdf.setFont('Helvetica', 8)
        pdf.drawCentredString(page_width / 2, 0.62 * inch, f'Verification Code: {self.certificate.verification_code}')

        # Add QR code to bottom-right corner
        try:
            qr_data = f"https://portal.velttech.org/verify/{self.certificate.certificate_number}/"
            qr_img = self.generate_qr_code(qr_data)
            
            # Save QR code to temporary file (ReportLab requires file path, not BytesIO)
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_qr:
                qr_img.save(temp_qr.name, format='PNG')
                qr_path = temp_qr.name
            
            # Place QR code in bottom-right corner
            qr_size = 0.9 * inch
            qr_x = page_width - qr_size - 0.5 * inch
            qr_y = 0.5 * inch
            
            pdf.drawImage(
                qr_path,
                qr_x,
                qr_y,
                width=qr_size,
                height=qr_size,
                preserveAspectRatio=True,
            )
            
            # Add "Scan to Verify" text below QR code
            pdf.setFillColor(dark)
            pdf.setFont('Helvetica-Bold', 8)
            pdf.drawCentredString(qr_x + qr_size / 2, qr_y - 0.18 * inch, 'Scan to Verify')
            
            # Clean up temporary file
            Path(qr_path).unlink(missing_ok=True)
        except Exception:
            # QR code generation failed, continue without it
            pass

        pdf.showPage()
        pdf.save()
        buffer.seek(0)
        return buffer.getvalue()

    def _get_student_name(self) -> str:
        """Get full student name"""
        names = [
            self.certificate.student.first_name,
            self.certificate.student.other_name,
            self.certificate.student.last_name,
        ]
        return ' '.join(name for name in names if name)

    def _get_status_display(self) -> str:
        """Get human-readable status"""
        if self.certificate.status == Certificate.STATUS_ISSUED:
            return 'Valid'
        elif self.certificate.status == Certificate.STATUS_REVOKED:
            return 'Revoked'
        else:
            return 'Draft'

    def _percentage_text(self, value) -> str:
        if value is None:
            return 'Not recorded'
        return f'{value}%'

    def save_to_certificate(self):
        """Generate PDF and save to certificate model"""
        pdf_bytes = self.generate_pdf()
        filename = f"{self.certificate.certificate_number}.pdf"
        self.certificate.certificate_file.save(
            filename,
            ContentFile(pdf_bytes),
            save=True
        )
