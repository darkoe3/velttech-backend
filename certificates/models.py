import uuid

from django.core.files.base import ContentFile
from django.db import models, transaction
from django.utils import timezone
from enrollments.models import Enrollment
from payments.models import Payment


class Certificate(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_ACTIVE = 'active'
    STATUS_ISSUED = STATUS_ACTIVE
    STATUS_LEGACY_ISSUED = 'issued'
    STATUS_REVOKED = 'revoked'

    TYPE_PARTICIPATION = 'participation'
    TYPE_COMPLETION = 'completion'
    TYPE_EXCELLENCE = 'excellence'

    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_ACTIVE, 'Active'),
        (STATUS_LEGACY_ISSUED, 'Issued (legacy)'),
        (STATUS_REVOKED, 'Revoked'),
    ]

    CERTIFICATE_TYPE_CHOICES = [
        (TYPE_PARTICIPATION, 'Participation'),
        (TYPE_COMPLETION, 'Completion'),
        (TYPE_EXCELLENCE, 'Excellence'),
    ]

    certificate_number = models.CharField(
        max_length=50,
        unique=True,
        editable=False,
    )
    student = models.ForeignKey(
        'students.Student',
        on_delete=models.CASCADE,
        related_name='certificates',
    )
    enrollment = models.OneToOneField(
        'enrollments.Enrollment',
        on_delete=models.CASCADE,
        related_name='certificate',
        unique=True,
    )
    course = models.ForeignKey(
        'courses.Course',
        on_delete=models.PROTECT,
        related_name='certificates',
    )
    issued_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        related_name='issued_certificates',
        null=True,
        blank=True,
    )
    issued_at = models.DateTimeField(blank=True, null=True)
    issue_date = models.DateField(blank=True, null=True)
    completion_date = models.DateField()
    certificate_type = models.CharField(
        max_length=20,
        choices=CERTIFICATE_TYPE_CHOICES,
        default=TYPE_COMPLETION,
    )
    final_score = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    final_grade = models.CharField(max_length=2, blank=True)
    attendance_percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    skills_covered = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    verification_code = models.CharField(
        max_length=36,
        unique=True,
        editable=False,
        default=uuid.uuid4,
    )
    qr_code = models.ImageField(
        upload_to='certificates/qr/',
        blank=True,
        null=True,
    )
    pdf_file = models.FileField(
        upload_to='certificates/',
        blank=True,
        null=True,
    )
    certificate_file = models.FileField(
        upload_to='certificates/',
        blank=True,
        null=True,
    )
    revoked_at = models.DateTimeField(blank=True, null=True)
    revoke_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'course'],
                name='unique_student_course_certificate',
            ),
        ]

    def __str__(self):
        return f'{self.certificate_number} - {self.student}'

    def save(self, *args, **kwargs):
        if not self.certificate_number:
            with transaction.atomic():
                year = self.issue_date.year if self.issue_date else timezone.localdate().year
                prefix = f'VTC-{year}-'
                last_cert = Certificate.objects.select_for_update().filter(
                    certificate_number__startswith=prefix,
                ).order_by('-certificate_number').first()
                last_sequence = int(last_cert.certificate_number.split('-')[-1]) if last_cert else 0
                self.certificate_number = f'{prefix}{last_sequence + 1:06d}'

        if self.status == self.STATUS_LEGACY_ISSUED:
            self.status = self.STATUS_ACTIVE

        if self.status == self.STATUS_ACTIVE and not self.issued_at:
            self.issued_at = timezone.now()
        if self.status == self.STATUS_ACTIVE and not self.issue_date:
            self.issue_date = timezone.localdate()
        if self.final_score is not None and not self.final_grade:
            if self.final_score >= 80:
                self.final_grade = 'A'
            elif self.final_score >= 70:
                self.final_grade = 'B'
            elif self.final_score >= 60:
                self.final_grade = 'C'
            elif self.final_score >= 50:
                self.final_grade = 'D'
            else:
                self.final_grade = 'F'

        super().save(*args, **kwargs)

    def is_eligible_for_certificate(self) -> bool:
        """
        Check if student is eligible for certificate:
        - Enrollment is completed
        - Student status is approved
        - All payments are paid (or no outstanding payments)
        """
        # Check enrollment status
        if self.enrollment.status != Enrollment.STATUS_COMPLETED:
            return False

        # Check student approval status
        if self.student.approval_status != self.student.STATUS_APPROVED:
            return False

        # Check payment status
        outstanding_payments = Payment.objects.filter(
            enrollment=self.enrollment,
            status=Payment.STATUS_PENDING,
        ).exists()

        return not outstanding_payments

    def is_active(self) -> bool:
        return self.status in {self.STATUS_ACTIVE, self.STATUS_LEGACY_ISSUED}

    def get_pdf_file(self):
        return self.pdf_file or self.certificate_file

    def verification_url(self) -> str:
        return f'https://portal.velttech.org/verify/{self.certificate_number}/'

    def generate_qr_code_file(self):
        import qrcode
        from io import BytesIO

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        qr.add_data(self.verification_url())
        qr.make(fit=True)
        image = qr.make_image(fill_color='black', back_color='white')
        buffer = BytesIO()
        image.save(buffer, format='PNG')
        self.qr_code.save(
            f'{self.certificate_number}-qr.png',
            ContentFile(buffer.getvalue()),
            save=False,
        )

    def revoke(self, reason: str = ''):
        """Revoke a certificate"""
        if self.is_active():
            self.status = self.STATUS_REVOKED
            self.revoked_at = timezone.now()
            self.revoke_reason = reason
            self.save()
            return True
        return False


class CertificateBranding(models.Model):
    academy_logo = models.ImageField(
        upload_to='certificates/branding/',
        blank=True,
        null=True,
        help_text='Optional logo used on generated certificate PDFs.',
    )
    director_signature = models.ImageField(
        upload_to='certificates/branding/',
        blank=True,
        null=True,
        help_text='Optional Academy Director signature used on generated certificate PDFs.',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Certificate branding'
        verbose_name_plural = 'Certificate branding'

    def __str__(self):
        return 'Certificate branding'

    @classmethod
    def current(cls):
        return cls.objects.order_by('pk').first()
