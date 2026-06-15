import tempfile
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.conf import settings
from .models import Certificate, CertificateBranding


# Velttech Brand Colors
GOLD = '#F4C318'
ORANGE = '#F28A1A'
GREEN = '#7AC943'
TECH_BLUE = '#9CCED9'
DARK = '#0F172A'
PROGRAMME_NAME = 'Young Innovators Academy'


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
        green = HexColor(GREEN)
        tech_blue = HexColor(TECH_BLUE)

        self._draw_double_border(pdf, page_width, page_height, gold)

        branding = CertificateBranding.current()
        logo_path = self._academy_logo_path(branding)
        logo_drawn = False
        if logo_path:
            logo_drawn = self._draw_image_fit(
                pdf,
                logo_path,
                (page_width - 1.75 * inch) / 2,
                page_height - 1.12 * inch,
                1.65 * inch,
                0.58 * inch,
            )
        if not logo_drawn:
            pdf.setFillColor(dark)
            pdf.setFont('Helvetica-Bold', 16)
            pdf.drawCentredString(page_width / 2, page_height - 0.82 * inch, 'VELTTECH')
            pdf.setFont('Helvetica-Bold', 14)
            pdf.drawCentredString(page_width / 2, page_height - 1.04 * inch, 'Young Innovators Academy')

        certificate_title = 'CERTIFICATE OF COMPLETION'
        pdf.setFillColor(gold)
        pdf.setFont('Times-Bold', 31)
        pdf.drawCentredString(page_width / 2, page_height - 1.78 * inch, certificate_title)
        pdf.setStrokeColor(orange)
        pdf.setLineWidth(0.8)
        pdf.line(page_width / 2 - 1.75 * inch, page_height - 1.96 * inch, page_width / 2 + 1.75 * inch, page_height - 1.96 * inch)

        pdf.setFillColor(dark)
        pdf.setFont('Helvetica', 12.5)
        pdf.drawCentredString(page_width / 2, page_height - 2.3 * inch, 'This is to certify that')

        pdf.setFont('Helvetica-Bold', 9.5)
        pdf.drawCentredString(page_width / 2, page_height - 2.62 * inch, 'AWARDED TO')

        pdf.setFillColor(orange)
        self._draw_fitted_centred_text(
            pdf,
            self._get_student_name().upper(),
            page_width / 2,
            page_height - 3.18 * inch,
            8.2 * inch,
            'Times-Bold',
            38,
            30,
        )

        issue_date = self.certificate.issue_date
        if not issue_date and self.certificate.issued_at:
            issue_date = self.certificate.issued_at.date()
        completion_date = self.certificate.completion_date or issue_date
        verification_url = self.certificate.verification_url()

        pdf.setFillColor(dark)
        pdf.setFont('Helvetica', 12.5)
        pdf.drawCentredString(page_width / 2, page_height - 3.76 * inch, 'has successfully completed the')

        pdf.setFillColor(gold)
        pdf.setFont('Times-Bold', 21)
        pdf.drawCentredString(page_width / 2, page_height - 4.16 * inch, PROGRAMME_NAME)

        detail_y = page_height - 4.76 * inch
        pdf.setFillColor(dark)
        pdf.setFont('Helvetica-Bold', 9.5)
        pdf.drawCentredString(page_width / 2, detail_y, 'SPECIALIZATION')
        pdf.setFillColor(dark)
        self._draw_fitted_centred_text(
            pdf,
            self._display_specialization(),
            page_width / 2,
            detail_y - 0.31 * inch,
            6.5 * inch,
            'Helvetica-Bold',
            16,
            12,
        )

        pdf.setFillColor(dark)
        pdf.setFont('Helvetica-Bold', 9.5)
        pdf.drawCentredString(page_width / 2, detail_y - 0.86 * inch, 'AWARDED ON')
        pdf.setFont('Helvetica', 13)
        pdf.drawCentredString(
            page_width / 2,
            detail_y - 1.16 * inch,
            completion_date.strftime('%d %B %Y') if completion_date else 'Not recorded',
        )

        pdf.setFillColor(tech_blue)
        pdf.setFont('Helvetica-Oblique', 9)
        pdf.drawCentredString(page_width / 2, 1.47 * inch, f'Verify online: {verification_url}')

        director_signature_path = self._file_field_path(getattr(branding, 'director_signature', None))
        self._draw_signature_block(
            pdf,
            1.35 * inch,
            1.08 * inch,
            2.35 * inch,
            'Academy Director',
            'Velttech Academy',
            director_signature_path,
            dark,
        )

        self._draw_certificate_metadata_block(
            pdf,
            page_width - 3.95 * inch,
            1.1 * inch,
            2.05 * inch,
            dark,
        )
        self._draw_academy_seal(pdf, page_width - 1.55 * inch, 2.03 * inch, 0.42 * inch, gold, orange, green, dark)

        # Add QR code to bottom-right corner
        try:
            qr_data = self.certificate.verification_url()
            qr_img = self.generate_qr_code(qr_data)
            
            # Save QR code to temporary file (ReportLab requires file path, not BytesIO)
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_qr:
                qr_img.save(temp_qr.name, format='PNG')
                qr_path = temp_qr.name
            
            # Place QR code in bottom-right corner
            qr_size = 0.9 * inch
            qr_x = page_width - qr_size - 0.7 * inch
            qr_y = 0.58 * inch
            
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

    def _display_specialization(self) -> str:
        return self.certificate.course.title.replace(' and ', ' & ')

    def _draw_double_border(self, pdf, page_width, page_height, color):
        from reportlab.lib.units import inch

        pdf.setStrokeColor(color)
        pdf.setLineWidth(1.6)
        pdf.rect(0.36 * inch, 0.36 * inch, page_width - 0.72 * inch, page_height - 0.72 * inch)
        pdf.setLineWidth(0.7)
        pdf.rect(0.53 * inch, 0.53 * inch, page_width - 1.06 * inch, page_height - 1.06 * inch)

    def _draw_fitted_centred_text(self, pdf, text, center_x, baseline_y, max_width, font_name, max_size, min_size):
        from reportlab.pdfbase.pdfmetrics import stringWidth

        font_size = max_size
        while font_size > min_size and stringWidth(text, font_name, font_size) > max_width:
            font_size -= 1
        pdf.setFont(font_name, font_size)
        pdf.drawCentredString(center_x, baseline_y, text)

    def _draw_wrapped_centred_text(self, pdf, text, center_x, start_y, max_width, line_height):
        from reportlab.pdfbase.pdfmetrics import stringWidth

        words = text.split()
        lines = []
        current = ''
        for word in words:
            candidate = f'{current} {word}'.strip()
            if stringWidth(candidate, 'Helvetica', 10.5) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)

        for index, line in enumerate(lines):
            pdf.drawCentredString(center_x, start_y - (index * line_height), line)

    def _academy_logo_path(self, branding):
        configured_logo = self._file_field_path(getattr(branding, 'academy_logo', None))
        if configured_logo:
            return configured_logo

        public_logo = Path(settings.BASE_DIR).parent / 'frontend' / 'public' / 'images' / 'velttech-logo.png'
        if public_logo.exists():
            return str(public_logo)
        return None

    def _file_field_path(self, field_file):
        if not field_file:
            return None
        try:
            path = field_file.path
        except (NotImplementedError, ValueError, AttributeError):
            return None
        return path if path and Path(path).exists() else None

    def _draw_image_fit(self, pdf, image_path, x, y, max_width, max_height):
        try:
            from reportlab.lib.utils import ImageReader

            image = ImageReader(image_path)
            image_width, image_height = image.getSize()
            scale = min(max_width / image_width, max_height / image_height)
            width = image_width * scale
            height = image_height * scale
            pdf.drawImage(
                image,
                x + (max_width - width) / 2,
                y + (max_height - height) / 2,
                width=width,
                height=height,
                preserveAspectRatio=True,
                mask='auto',
            )
            return True
        except Exception:
            return False

    def _draw_signature_block(self, pdf, x, line_y, width, label, sublabel, signature_path, color):
        from reportlab.lib.units import inch

        if signature_path:
            self._draw_image_fit(
                pdf,
                signature_path,
                x + 0.15 * inch,
                line_y + 0.08 * inch,
                width - 0.3 * inch,
                0.46 * inch,
            )

        pdf.setStrokeColor(color)
        pdf.setLineWidth(1)
        pdf.line(x, line_y, x + width, line_y)
        pdf.setFillColor(color)
        pdf.setFont('Helvetica-Bold', 10)
        pdf.drawCentredString(x + width / 2, line_y - 0.22 * inch, label)
        pdf.setFont('Helvetica', 8.5)
        pdf.drawCentredString(x + width / 2, line_y - 0.42 * inch, sublabel)

    def _draw_certificate_metadata_block(self, pdf, x, line_y, width, color):
        from reportlab.lib.units import inch

        center_x = x + width / 2
        pdf.setFillColor(color)
        pdf.setFont('Helvetica-Bold', 10)
        pdf.drawCentredString(center_x, line_y + 0.52 * inch, 'Certificate No.')
        pdf.setFont('Helvetica', 9)
        pdf.drawCentredString(center_x, line_y + 0.31 * inch, self.certificate.certificate_number)
        pdf.setFont('Helvetica-Bold', 10)
        pdf.drawCentredString(center_x, line_y + 0.04 * inch, 'Verification Code')
        pdf.setFont('Helvetica', 7.5)
        pdf.drawCentredString(center_x, line_y - 0.17 * inch, str(self.certificate.verification_code))

    def _draw_academy_seal(self, pdf, center_x, center_y, radius, gold, orange, green, dark):
        from reportlab.lib.units import inch

        pdf.setStrokeColor(gold)
        pdf.setLineWidth(1.2)
        pdf.circle(center_x, center_y, radius)
        pdf.setStrokeColor(orange)
        pdf.setLineWidth(0.8)
        pdf.circle(center_x, center_y, radius - 0.08 * inch)
        pdf.setStrokeColor(green)
        pdf.setLineWidth(0.8)
        pdf.circle(center_x, center_y, radius - 0.18 * inch)
        pdf.setFillColor(dark)
        pdf.setFont('Helvetica-Bold', 6.6)
        pdf.drawCentredString(center_x, center_y + 0.1 * inch, 'VELTTECH ACADEMY')
        pdf.setFillColor(orange)
        pdf.setFont('Helvetica-Bold', 8.2)
        pdf.drawCentredString(center_x, center_y - 0.1 * inch, 'CERTIFIED')

    def _skills(self):
        if self.certificate.skills_covered:
            return self.certificate.skills_covered

        title = self.certificate.course.title.lower()
        if 'web' in title:
            return ['HTML', 'CSS', 'JavaScript', 'Responsive Design']
        if 'robot' in title or 'arduino' in title:
            return ['Arduino Programming', 'Electronics Fundamentals', 'Robotics Design']
        if 'coding' in title or 'scratch' in title or 'kids' in title:
            return ['Computational Thinking', 'Scratch Programming', 'Problem Solving', 'Digital Citizenship']
        return []

    def save_to_certificate(self):
        """Generate PDF and save to certificate model"""
        if not self.certificate.qr_code:
            self.certificate.generate_qr_code_file()
        pdf_bytes = self.generate_pdf()
        filename = f"{self.certificate.certificate_number}.pdf"
        self.certificate.pdf_file.save(
            filename,
            ContentFile(pdf_bytes),
            save=False
        )
        if not self.certificate.certificate_file:
            self.certificate.certificate_file.save(
                filename,
                ContentFile(pdf_bytes),
                save=False,
            )
        self.certificate.save()
