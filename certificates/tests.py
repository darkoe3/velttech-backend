from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from datetime import date
from decimal import Decimal
from unittest.mock import patch
import base64

from rest_framework.test import APIClient

from courses.models import Course
from students.models import Student, Parent
from enrollments.models import Assignment, AssignmentSubmission, AssessmentResult, Attendance, Enrollment
from payments.models import Payment
from users.models import ActivityLog
from notifications.models import Notification
from .models import Certificate, CertificateBranding
from .services import check_combined_result_certificate_eligibility

User = get_user_model()
TINY_PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAFgwJ/lxJd4wAAAABJRU5ErkJggg=='
)


class CertificateModelTests(TestCase):
    def setUp(self):
        """Set up test data"""
        # Create users
        self.admin_user = User.objects.create_user(
            email='admin@test.com',
            password='testpass123',
            first_name='Admin',
            last_name='User',
            role='admin',
            approval_status='approved',
        )
        self.instructor = User.objects.create_user(
            email='instructor@test.com',
            password='testpass123',
            first_name='Instructor',
            last_name='User',
            role='instructor',
            approval_status='approved',
        )
        self.student_user = User.objects.create_user(
            email='student@test.com',
            password='testpass123',
            first_name='Student',
            last_name='User',
            role='student',
            approval_status='approved',
        )
        self.parent_user = User.objects.create_user(
            email='parentuser@test.com',
            password='testpass123',
            first_name='Parent',
            last_name='Account',
            role='parent',
            approval_status='approved',
        )
        self.other_instructor = User.objects.create_user(
            email='other-instructor@test.com',
            password='testpass123',
            first_name='Other',
            last_name='Instructor',
            role='instructor',
            approval_status='approved',
        )

        # Create course
        self.course = Course.objects.create(
            title='Test Course',
            description='A test course',
            duration_months=3,
            monthly_fee=100.00,
        )

        # Create parent and student
        self.parent = Parent.objects.create(
            user=self.parent_user,
            first_name='Parent',
            last_name='User',
            email='parent@test.com',
            phone_number='1234567890',
        )

        self.student = Student.objects.create(
            user=self.student_user,
            parent=self.parent,
            first_name='Student',
            last_name='User',
            email='student@test.com',
            learner_type='child',
            approval_status='approved',
        )

        # Create enrollment
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course,
            instructor=self.instructor,
            status='completed',
        )

        # Create paid payment
        self.payment = Payment.objects.create(
            enrollment=self.enrollment,
            amount=300.00,
            status='paid',
        )

    def test_certificate_creation(self):
        """Test creating a certificate"""
        cert = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ISSUED,
            issued_by=self.admin_user,
            issued_at=timezone.now(),
        )

        self.assertIsNotNone(cert.certificate_number)
        self.assertTrue(cert.certificate_number.startswith('VTC-'))
        self.assertIsNotNone(cert.verification_code)
        self.assertEqual(cert.certificate_type, Certificate.TYPE_COMPLETION)
        self.assertIsNotNone(cert.issue_date)

    def test_duplicate_issued_certificate_is_blocked(self):
        """Test that a second certificate cannot be created for the same enrollment"""
        cert1 = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ISSUED,
            issued_by=self.admin_user,
        )

        with self.assertRaises(Exception):
            Certificate.objects.create(
                student=self.student,
                enrollment=self.enrollment,
                course=self.course,
                completion_date=date.today(),
                status=Certificate.STATUS_ISSUED,
                issued_by=self.admin_user,
            )

    def test_certificate_uniqueness_is_per_enrollment_not_student_course(self):
        constraint_names = {constraint.name for constraint in Certificate._meta.constraints}

        self.assertNotIn('unique_student_course_certificate', constraint_names)
        self.assertTrue(Certificate._meta.get_field('enrollment').one_to_one)

    def test_eligibility_check(self):
        """Test certificate eligibility check"""
        cert = Certificate(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
        )

        # Should be eligible with completed enrollment, approved student, and paid payment
        self.assertTrue(cert.is_eligible_for_certificate())

        # Change student status to pending
        self.student.approval_status = 'pending'
        self.student.save()
        self.assertFalse(cert.is_eligible_for_certificate())

        # Reset student status
        self.student.approval_status = 'approved'
        self.student.save()

        # Change enrollment status
        self.enrollment.status = 'active'
        self.enrollment.save()
        self.assertFalse(cert.is_eligible_for_certificate())

    def test_certificate_revocation(self):
        """Test revoking a certificate"""
        cert = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ISSUED,
            issued_by=self.admin_user,
        )

        self.assertEqual(cert.status, Certificate.STATUS_ISSUED)
        self.assertIsNone(cert.revoked_at)

        # Revoke certificate
        result = cert.revoke(reason='Test revocation')
        self.assertTrue(result)
        self.assertEqual(cert.status, Certificate.STATUS_REVOKED)
        self.assertIsNotNone(cert.revoked_at)
        self.assertEqual(cert.revoke_reason, 'Test revocation')

    def test_certificate_pdf_contains_required_metadata(self):
        from .pdf_generator import CertificatePDFGenerator

        cert = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ISSUED,
            issued_by=self.admin_user,
            certificate_type=Certificate.TYPE_EXCELLENCE,
            final_score=95,
            final_grade='A',
            attendance_percentage=92,
        )

        pdf_bytes = CertificatePDFGenerator(cert).generate_pdf()

        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
        self.assertGreater(len(pdf_bytes), 1000)

    def test_combined_result_eligibility_allows_approved_passing_result(self):
        result = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
        )

        eligibility = check_combined_result_certificate_eligibility(self.enrollment)

        self.assertEqual(result.status, AssessmentResult.STATUS_APPROVED)
        self.assertTrue(eligibility['eligible'])
        self.assertEqual(eligibility['reasons'], [])
        self.assertEqual(eligibility['percentage'], Decimal('80.00'))

    def test_pending_payment_blocks_combined_result_eligibility(self):
        AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
        )
        self.payment.status = Payment.STATUS_PENDING
        self.payment.save(update_fields=['status'])

        eligibility = check_combined_result_certificate_eligibility(self.enrollment)

        self.assertFalse(eligibility['eligible'])
        self.assertFalse(eligibility['payments_settled'])
        self.assertIn('Payments are not settled.', eligibility['reasons'])

    def test_incomplete_enrollment_blocks_combined_result_eligibility(self):
        AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
        )
        self.enrollment.status = Enrollment.STATUS_ACTIVE
        self.enrollment.save(update_fields=['status'])

        eligibility = check_combined_result_certificate_eligibility(self.enrollment)

        self.assertFalse(eligibility['eligible'])
        self.assertFalse(eligibility['enrollment_completed'])
        self.assertIn('Enrollment is not completed.', eligibility['reasons'])

    def test_duplicate_certificate_blocks_combined_result_eligibility(self):
        AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
        )
        Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ACTIVE,
            issued_by=self.admin_user,
        )

        eligibility = check_combined_result_certificate_eligibility(self.enrollment)

        self.assertFalse(eligibility['eligible'])
        self.assertTrue(eligibility['certificate_exists'])
        self.assertIn('Certificate already issued.', eligibility['reasons'])

    def test_revoked_certificate_blocks_new_issue_and_recommends_reissue(self):
        AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
        )
        certificate = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_REVOKED,
            issued_by=self.admin_user,
        )

        eligibility = check_combined_result_certificate_eligibility(self.enrollment)

        self.assertFalse(eligibility['eligible'])
        self.assertFalse(eligibility['certificate_exists'])
        self.assertTrue(eligibility['certificate_revoked'])
        self.assertEqual(eligibility['certificate_id'], certificate.id)
        self.assertEqual(eligibility['certificate_number'], certificate.certificate_number)
        self.assertEqual(eligibility['certificate_status'], Certificate.STATUS_REVOKED)
        self.assertEqual(eligibility['recommended_action'], 'reissue')
        self.assertIn('Certificate revoked — use Reissue.', eligibility['reasons'])

    def test_missing_score_components_are_reported_separately(self):
        AssessmentResult.objects.create(
            enrollment=self.enrollment,
            final_project_score=Decimal('30.00'),
        )

        eligibility = check_combined_result_certificate_eligibility(self.enrollment)

        self.assertFalse(eligibility['eligible'])
        self.assertIn('Practical score missing.', eligibility['reasons'])
        self.assertIn('Objective Quiz score missing.', eligibility['reasons'])
        self.assertNotIn('Final Project score missing.', eligibility['reasons'])

    def test_certificate_from_another_enrollment_does_not_block_eligibility(self):
        Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ACTIVE,
            issued_by=self.admin_user,
        )
        second_course = Course.objects.create(
            title='Second Course',
            description='Another test course',
            duration_months=2,
            monthly_fee=150.00,
        )
        second_enrollment = Enrollment.objects.create(
            student=self.student,
            course=second_course,
            instructor=self.instructor,
            status=Enrollment.STATUS_COMPLETED,
        )
        Payment.objects.create(
            enrollment=second_enrollment,
            amount=300.00,
            status=Payment.STATUS_PAID,
        )
        AssessmentResult.objects.create(
            enrollment=second_enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
        )

        eligibility = check_combined_result_certificate_eligibility(second_enrollment)

        self.assertTrue(eligibility['eligible'])
        self.assertFalse(eligibility['certificate_exists'])
        self.assertEqual(eligibility['reasons'], [])

    def test_current_branding_uses_latest_record(self):
        older_branding = CertificateBranding.objects.create()
        newer_branding = CertificateBranding.objects.create()

        self.assertEqual(CertificateBranding.current(), newer_branding)
        self.assertNotEqual(CertificateBranding.current(), older_branding)

    def test_director_signature_is_loaded_from_storage_for_pdf_generation(self):
        from .pdf_generator import CertificatePDFGenerator

        branding = CertificateBranding.objects.create()
        branding.director_signature.save('director.png', ContentFile(TINY_PNG), save=True)
        cert = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ISSUED,
            issued_by=self.admin_user,
        )

        with patch.object(CertificatePDFGenerator, '_draw_signature_block', autospec=True) as signature_block:
            pdf_bytes = CertificatePDFGenerator(cert).generate_pdf()

        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
        signature_block.assert_called_once()
        args = signature_block.call_args.args
        self.assertEqual(args[5], 'Academy Director')
        self.assertEqual(args[6], 'Velttech Academy')
        self.assertIsNotNone(args[7])
        self.assertNotIn('Instructor', [args[5], args[6]])

    def test_missing_director_signature_file_falls_back_without_crashing(self):
        from .pdf_generator import CertificatePDFGenerator

        branding = CertificateBranding.objects.create()
        branding.director_signature.save('missing-director.png', ContentFile(TINY_PNG), save=True)
        missing_name = branding.director_signature.name
        branding.director_signature.storage.delete(missing_name)
        cert = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ISSUED,
            issued_by=self.admin_user,
        )

        with self.assertLogs('certificates.pdf_generator', level='WARNING') as logs:
            pdf_bytes = CertificatePDFGenerator(cert).generate_pdf()

        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
        self.assertTrue(any('missing from storage' in message for message in logs.output))

    def test_no_director_signature_configured_uses_fallback_label(self):
        from .pdf_generator import CertificatePDFGenerator
        from reportlab import rl_config

        CertificateBranding.objects.create()
        cert = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ISSUED,
            issued_by=self.admin_user,
        )

        original_compression = rl_config.pageCompression
        rl_config.pageCompression = 0
        try:
            pdf_bytes = CertificatePDFGenerator(cert).generate_pdf()
        finally:
            rl_config.pageCompression = original_compression

        self.assertIn('Academy Director', pdf_bytes.decode('latin-1', errors='ignore'))


@override_settings(
    MIDDLEWARE=[],
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    FRONTEND_URL='https://academy.test',
)
class CertificateAPITests(CertificateModelTests):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_admin_issues_certificate(self, generator_cls):
        generator_cls.return_value.save_to_certificate.return_value = None
        self._create_approved_assessment_result()
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
            'certificate_type': Certificate.TYPE_EXCELLENCE,
            'final_score': '95.00',
            'final_grade': 'A',
            'attendance_percentage': '90.00',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], Certificate.STATUS_ACTIVE)
        self.assertEqual(response.data['certificate_type'], Certificate.TYPE_EXCELLENCE)
        self.assertEqual(response.data['final_grade'], 'A')
        self.assertEqual(Certificate.objects.count(), 1)
        self.assertTrue(ActivityLog.objects.filter(action='Certificate issued').exists())
        certificate = Certificate.objects.get()
        certificate.refresh_from_db()
        self.assertIsNotNone(certificate.certificate_email_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            'Congratulations! Student User has completed Young Innovators Academy',
        )
        self.assertEqual(mail.outbox[0].to, [self.parent.email])
        self.assertEqual(mail.outbox[0].attachments, [])
        self.assertIn('parent portal', mail.outbox[0].body)
        self.assertIn('https://academy.test/login', mail.outbox[0].body)
        self.assertTrue(Notification.objects.filter(
            recipient=self.parent_user,
            title='Certificate Issued',
            message='A certificate has been issued for Student User.',
        ).exists())

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_assigned_instructor_issues_eligible_certificate(self, generator_cls):
        def save_generated_pdf():
            certificate = Certificate.objects.get()
            certificate.pdf_file.save(
                f'{certificate.certificate_number}.pdf',
                ContentFile(b'%PDF-1.4 instructor certificate'),
                save=True,
            )

        generator_cls.return_value.save_to_certificate.side_effect = save_generated_pdf
        assessment_result = self._create_approved_assessment_result(approved_by=self.instructor)
        self.client.force_authenticate(self.instructor)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'assessment_result_id': assessment_result.id,
            'completion_date': date.today().isoformat(),
        }, format='json')
        duplicate_response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'assessment_result_id': assessment_result.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(duplicate_response.status_code, 400)
        certificate = Certificate.objects.get(enrollment=self.enrollment)
        self.assertEqual(certificate.issued_by, self.instructor)
        self.assertTrue(certificate.pdf_file.storage.exists(certificate.pdf_file.name))
        self.assertEqual(Certificate.objects.count(), 1)
        assessment_result.refresh_from_db()
        self.assertEqual(assessment_result.status, AssessmentResult.STATUS_CERTIFICATE_ISSUED)

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_same_learner_can_receive_certificates_for_multiple_course_enrollments(self, generator_cls):
        generator_cls.return_value.save_to_certificate.return_value = None
        first_result = self._create_approved_assessment_result()

        def create_ready_enrollment(course_title):
            course = Course.objects.create(
                title=course_title,
                description=f'{course_title} description',
                duration_months=2,
                monthly_fee=150.00,
            )
            enrollment = Enrollment.objects.create(
                student=self.student,
                course=course,
                instructor=self.instructor,
                status=Enrollment.STATUS_COMPLETED,
            )
            Payment.objects.create(
                enrollment=enrollment,
                amount=300.00,
                status=Payment.STATUS_PAID,
            )
            AssessmentResult.objects.create(
                enrollment=enrollment,
                practical_score=Decimal('35.00'),
                final_project_score=Decimal('30.00'),
                objective_quiz_score=Decimal('15.00'),
                is_approved=True,
                approved_by=self.admin_user,
                approved_at=timezone.now(),
            )
            return enrollment

        second_enrollment = create_ready_enrollment('Second Certificate Course')
        third_enrollment = create_ready_enrollment('Third Certificate Course')
        self.client.force_authenticate(self.admin_user)

        responses = [
            self.client.post(reverse('certificate-issue'), {
                'enrollment_id': enrollment.id,
                'assessment_result_id': getattr(enrollment, 'assessment_result', first_result).id,
                'completion_date': date.today().isoformat(),
            }, format='json')
            for enrollment in [self.enrollment, second_enrollment, third_enrollment]
        ]

        self.assertEqual([response.status_code for response in responses], [201, 201, 201])
        self.assertEqual(Certificate.objects.count(), 3)
        self.assertEqual(
            set(Certificate.objects.values_list('enrollment_id', flat=True)),
            {self.enrollment.id, second_enrollment.id, third_enrollment.id},
        )

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_existing_certificate_from_another_enrollment_does_not_block_instructor_issue(self, generator_cls):
        generator_cls.return_value.save_to_certificate.return_value = None
        self._create_approved_assessment_result()
        Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ACTIVE,
            issued_by=self.admin_user,
        )
        next_course = Course.objects.create(
            title='Instructor Second Certificate Course',
            description='Second course',
            duration_months=2,
            monthly_fee=150.00,
        )
        next_enrollment = Enrollment.objects.create(
            student=self.student,
            course=next_course,
            instructor=self.instructor,
            status=Enrollment.STATUS_COMPLETED,
        )
        Payment.objects.create(
            enrollment=next_enrollment,
            amount=300.00,
            status=Payment.STATUS_PAID,
        )
        next_result = AssessmentResult.objects.create(
            enrollment=next_enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.instructor,
            approved_at=timezone.now(),
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': next_enrollment.id,
            'assessment_result_id': next_result.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Certificate.objects.count(), 2)
        self.assertTrue(Certificate.objects.filter(enrollment=next_enrollment).exists())

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_adult_learner_receives_certificate_notification(self, generator_cls):
        generator_cls.return_value.save_to_certificate.return_value = None
        adult_user = User.objects.create_user(
            email='adult@test.com',
            password='testpass123',
            first_name='Adult',
            last_name='Learner',
            role='student',
            account_type='adult_learner',
            approval_status='approved',
        )
        adult_student = Student.objects.create(
            user=adult_user,
            first_name='Adult',
            last_name='Learner',
            email='adult-profile@test.com',
            learner_type=Student.LEARNER_ADULT,
            approval_status='approved',
        )
        adult_enrollment = Enrollment.objects.create(
            student=adult_student,
            course=self.course,
            instructor=self.instructor,
            status='completed',
        )
        Payment.objects.create(
            enrollment=adult_enrollment,
            amount=300.00,
            status='paid',
        )
        AssessmentResult.objects.create(
            enrollment=adult_enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
        )
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': adult_enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 201)
        certificate = Certificate.objects.get(enrollment=adult_enrollment)
        self.assertIsNotNone(certificate.certificate_email_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Your Velttech Academy Certificate Is Ready')
        self.assertEqual(mail.outbox[0].to, [adult_user.email])
        self.assertEqual(mail.outbox[0].attachments, [])
        self.assertIn('student dashboard', mail.outbox[0].body)
        self.assertTrue(Notification.objects.filter(
            recipient=adult_user,
            title='Certificate Ready',
            message='Your certificate for Young Innovators Academy is now available.',
        ).exists())

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_certificate_notification_is_not_duplicated(self, generator_cls):
        from .notifications import send_certificate_issued_notification

        generator_cls.return_value.save_to_certificate.return_value = None
        self._create_approved_assessment_result()
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 201)
        certificate = Certificate.objects.get()
        first_sent_at = certificate.certificate_email_sent_at
        certificate.completion_date = date.today()
        certificate.save()
        sent_again = send_certificate_issued_notification(certificate)
        certificate.refresh_from_db()

        self.assertFalse(sent_again)
        self.assertEqual(certificate.certificate_email_sent_at, first_sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.parent_user).count(), 1)

    @patch('certificates.notifications.logger')
    @patch('certificates.notifications.send_mail')
    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_certificate_issuance_succeeds_when_notification_email_fails(self, generator_cls, send_mail_mock, logger_mock):
        generator_cls.return_value.save_to_certificate.return_value = None
        send_mail_mock.side_effect = RuntimeError('SMTP unavailable')
        self._create_approved_assessment_result()
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 201)
        certificate = Certificate.objects.get()
        self.assertIsNone(certificate.certificate_email_sent_at)
        self.assertTrue(Notification.objects.filter(recipient=self.parent_user).exists())
        self.assertTrue(ActivityLog.objects.filter(action='certificate_email_failed').exists())
        logger_mock.exception.assert_called_once()

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_instructor_can_only_issue_assigned_certificate(self, generator_cls):
        generator_cls.return_value.save_to_certificate.return_value = None
        self._create_approved_assessment_result()
        self.client.force_authenticate(self.other_instructor)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 403)

    def test_instructor_cannot_issue_ineligible_certificate(self):
        self._create_approved_assessment_result()
        self.payment.status = Payment.STATUS_PENDING
        self.payment.save(update_fields=['status'])
        self.client.force_authenticate(self.instructor)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Payments are not settled.', response.data['reasons'])
        self.assertEqual(Certificate.objects.count(), 0)

    def test_parent_cannot_issue_certificate(self):
        self._create_approved_assessment_result()
        self.client.force_authenticate(self.parent_user)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Certificate.objects.count(), 0)

    def test_student_cannot_issue_certificate(self):
        self._create_approved_assessment_result()
        self.client.force_authenticate(self.student_user)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Certificate.objects.count(), 0)

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_duplicate_certificate_is_blocked(self, generator_cls):
        generator_cls.return_value.save_to_certificate.return_value = None
        self._create_approved_assessment_result()
        self.client.force_authenticate(self.admin_user)
        payload = {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }

        first = self.client.post(reverse('certificate-issue'), payload, format='json')
        second = self.client.post(reverse('certificate-issue'), payload, format='json')

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)

    def test_revoked_certificate_is_not_offered_for_new_issuance(self):
        self._create_approved_assessment_result()
        certificate = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_REVOKED,
            issued_by=self.admin_user,
        )
        self.client.force_authenticate(self.admin_user)

        eligible_response = self.client.get(reverse('certificate-eligible'), {'course_id': self.course.id})
        issue_response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(eligible_response.status_code, 200)
        self.assertEqual(eligible_response.data['eligible_students'], [])
        self.assertIn(
            {
                'code': 'certificate_revoked',
                'label': 'Certificate revoked — use Reissue',
                'count': 1,
            },
            eligible_response.data['summary']['blockers'],
        )
        self.assertEqual(issue_response.status_code, 400)
        self.assertIn('Certificate revoked — use Reissue.', issue_response.data['reasons'])
        self.assertEqual(Certificate.objects.count(), 1)
        self.assertEqual(Certificate.objects.get().id, certificate.id)

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_revoked_certificate_can_still_use_existing_reissue(self, generator_cls):
        generator_cls.return_value.save_to_certificate.return_value = None
        certificate = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_REVOKED,
            issued_by=self.admin_user,
        )
        certificate_number = certificate.certificate_number
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(reverse('certificate-reissue', args=[certificate.id]))

        self.assertEqual(response.status_code, 200)
        certificate.refresh_from_db()
        self.assertEqual(Certificate.objects.count(), 1)
        self.assertEqual(certificate.certificate_number, certificate_number)
        self.assertEqual(certificate.status, Certificate.STATUS_ACTIVE)

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_result_status_becomes_certificate_issued_after_issue(self, generator_cls):
        generator_cls.return_value.save_to_certificate.return_value = None
        self.assessment_result = self._create_approved_assessment_result()
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'assessment_result_id': self.assessment_result.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assessment_result.refresh_from_db()
        self.assertEqual(self.assessment_result.status, AssessmentResult.STATUS_CERTIFICATE_ISSUED)

    def test_incomplete_result_cannot_issue_certificate(self):
        self.assessment_result = self._create_approved_assessment_result()
        self.assessment_result.practical_score = None
        self.assessment_result.is_approved = False
        self.assessment_result.save()
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Practical score missing.', response.data['reasons'])

    def test_unapproved_result_cannot_issue_certificate(self):
        self.assessment_result = self._create_approved_assessment_result()
        self.assessment_result.is_approved = False
        self.assessment_result.approved_by = None
        self.assessment_result.approved_at = None
        self.assessment_result.save()
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Combined assessment result is not approved.', response.data['reasons'])

    def test_outstanding_payment_blocks_issuance(self):
        self._create_approved_assessment_result()
        self.payment.status = Payment.STATUS_PENDING
        self.payment.save(update_fields=['status'])
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('Payments are not settled.', response.data['reasons'])

    def test_student_downloads_own_certificate(self):
        cert = self._create_certificate_with_file()
        self.client.force_authenticate(self.student_user)

        response = self.client.get(reverse('certificate-download', args=[cert.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(
            response['Content-Disposition'],
            f'attachment; filename="{cert.certificate_number}.pdf"',
        )
        self.assertTrue(self._response_bytes(response).startswith(b'%PDF'))
        self.assertTrue(ActivityLog.objects.filter(action='Certificate downloaded').exists())

    def test_parent_downloads_child_certificate(self):
        cert = self._create_certificate_with_file()
        self.client.force_authenticate(self.parent_user)

        response = self.client.get(reverse('certificate-download', args=[cert.id]))

        self.assertEqual(response.status_code, 200)

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_download_regenerates_missing_pdf_file(self, generator_cls):
        cert = self._create_certificate_with_file()
        missing_name = cert.certificate_file.name
        cert.certificate_file.storage.delete(missing_name)
        self.assertFalse(cert.certificate_file.storage.exists(missing_name))

        def save_regenerated_pdf():
            cert.refresh_from_db()
            cert.pdf_file.save(
                f'{cert.certificate_number}.pdf',
                ContentFile(b'%PDF-1.4 regenerated certificate'),
                save=True,
            )

        generator_cls.return_value.save_to_certificate.side_effect = save_regenerated_pdf
        self.client.force_authenticate(self.student_user)

        response = self.client.get(reverse('certificate-download', args=[cert.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(self._response_bytes(response).startswith(b'%PDF'))
        generator_cls.assert_called_once()
        cert.refresh_from_db()
        self.assertTrue(cert.pdf_file.storage.exists(cert.pdf_file.name))

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_download_generates_pdf_when_no_file_field_is_set(self, generator_cls):
        cert = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ISSUED,
            issued_by=self.admin_user,
        )

        def save_generated_pdf():
            cert.refresh_from_db()
            cert.pdf_file.save(
                f'{cert.certificate_number}.pdf',
                ContentFile(b'%PDF-1.4 generated certificate'),
                save=True,
            )

        generator_cls.return_value.save_to_certificate.side_effect = save_generated_pdf
        self.client.force_authenticate(self.student_user)

        response = self.client.get(reverse('certificate-download', args=[cert.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._response_bytes(response).startswith(b'%PDF'))
        generator_cls.assert_called_once()
        cert.refresh_from_db()
        self.assertTrue(cert.pdf_file.storage.exists(cert.pdf_file.name))

    def test_download_regenerated_pdf_uses_director_signature_when_available(self):
        from .pdf_generator import CertificatePDFGenerator

        branding = CertificateBranding.objects.create()
        branding.director_signature.save('download-director.png', ContentFile(TINY_PNG), save=True)
        cert = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ISSUED,
            issued_by=self.admin_user,
        )
        cert.qr_code.save('download-qr.png', ContentFile(TINY_PNG), save=True)
        self.client.force_authenticate(self.student_user)

        with patch.object(CertificatePDFGenerator, '_draw_signature_block', autospec=True) as signature_block:
            response = self.client.get(reverse('certificate-download', args=[cert.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(self._response_bytes(response).startswith(b'%PDF'))
        signature_block.assert_called_once()
        self.assertIsNotNone(signature_block.call_args.args[7])
        cert.refresh_from_db()
        self.assertTrue(cert.pdf_file.storage.exists(cert.pdf_file.name))

    @patch('certificates.views.logger')
    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_download_regeneration_failure_returns_clean_error(self, generator_cls, logger_mock):
        cert = self._create_certificate_with_file()
        missing_name = cert.certificate_file.name
        cert.certificate_file.storage.delete(missing_name)
        generator_cls.return_value.save_to_certificate.side_effect = RuntimeError('PDF generator failed')
        self.client.force_authenticate(self.student_user)

        response = self.client.get(reverse('certificate-download', args=[cert.id]))

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.data['detail'],
            'The certificate PDF could not be prepared. Please contact Velttech support.',
        )
        self.assertNotIn('PDF generator failed', str(response.data))
        self.assertNotIn('traceback', str(response.data).lower())
        logger_mock.exception.assert_called_once()

    def test_instructor_downloads_assigned_certificate(self):
        cert = self._create_certificate_with_file()
        self.client.force_authenticate(self.instructor)

        response = self.client.get(reverse('certificate-download', args=[cert.id]))

        self.assertEqual(response.status_code, 200)

    def test_instructor_cannot_download_unassigned_certificate(self):
        cert = self._create_other_student_certificate_with_file()
        self.client.force_authenticate(self.other_instructor)

        response = self.client.get(reverse('certificate-download', args=[cert.id]))

        self.assertEqual(response.status_code, 404)

    def test_student_cannot_download_another_students_certificate(self):
        cert = self._create_other_student_certificate_with_file()
        self.client.force_authenticate(self.student_user)

        response = self.client.get(reverse('certificate-download', args=[cert.id]))

        self.assertEqual(response.status_code, 404)

    def test_parent_cannot_download_unlinked_child_certificate(self):
        cert = self._create_other_student_certificate_with_file()
        self.client.force_authenticate(self.parent_user)

        response = self.client.get(reverse('certificate-download', args=[cert.id]))

        self.assertEqual(response.status_code, 404)

    def test_public_verification_and_revoked_status(self):
        cert = self._create_certificate_with_file()
        cert.revoke('Administrative correction')

        response = self.client.get(reverse('certificate-verify', args=[cert.verification_code]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], Certificate.STATUS_REVOKED)
        self.assertEqual(response.data['status_label'], 'Revoked')
        self.assertEqual(response.data['certificate_number'], cert.certificate_number)
        self.assertNotIn('final_score', response.data)
        self.assertNotIn('final_grade', response.data)
        self.assertNotIn('attendance_percentage', response.data)
        self.assertTrue(ActivityLog.objects.filter(action='Certificate verified').exists())

    def test_public_verification_by_certificate_number(self):
        cert = self._create_certificate_with_file()

        response = self.client.get(reverse('certificate-verify', args=[cert.certificate_number]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['certificate_number'], cert.certificate_number)
        self.assertEqual(response.data['student_name'], 'Student User')
        self.assertEqual(response.data['programme_name'], 'Young Innovators Academy')
        self.assertEqual(response.data['specialization_title'], self.course.title)
        self.assertEqual(response.data['course_title'], self.course.title)
        self.assertEqual(response.data['issued_by_name'], 'Velttech Academy')
        self.assertEqual(response.data['status_label'], 'Valid')

    def test_certificate_list_keeps_assessment_metrics_off_certificate_surface(self):
        cert = self._create_certificate_with_file()
        self.client.force_authenticate(self.student_user)

        response = self.client.get(reverse('certificate-list'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['certificate_number'], cert.certificate_number)
        self.assertEqual(response.data[0]['programme_name'], 'Young Innovators Academy')
        self.assertEqual(response.data[0]['specialization_title'], self.course.title)
        self.assertNotIn('final_score', response.data[0])
        self.assertNotIn('final_grade', response.data[0])
        self.assertNotIn('attendance_percentage', response.data[0])

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_issue_certificate_calculates_score_grade_and_attendance(self, generator_cls):
        generator_cls.return_value.save_to_certificate.return_value = None
        self._create_approved_assessment_result()
        assignment = Assignment.objects.create(
            title='Final Project',
            description='Build a project.',
            course=self.course,
            instructor=self.instructor,
            due_date=date.today(),
            submission_type=Assignment.ASSESSMENT_PRACTICAL,
            marks=100,
        )
        AssignmentSubmission.objects.create(
            assignment=assignment,
            student=self.student,
            score=85,
            max_score=100,
            status=AssignmentSubmission.STATUS_GRADED,
        )
        Attendance.objects.create(
            enrollment=self.enrollment,
            date=date(2026, 6, 1),
            status=Attendance.STATUS_PRESENT,
            recorded_by=self.instructor,
        )
        Attendance.objects.create(
            enrollment=self.enrollment,
            date=date(2026, 6, 2),
            status=Attendance.STATUS_ABSENT,
            recorded_by=self.instructor,
        )
        self.client.force_authenticate(self.admin_user)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['final_score'], '80.00')
        self.assertEqual(response.data['final_grade'], 'A')
        self.assertEqual(response.data['attendance_percentage'], '50.00')

    def test_certificate_pdf_still_excludes_assessment_metrics(self):
        from .pdf_generator import CertificatePDFGenerator
        from reportlab import rl_config

        cert = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ISSUED,
            issued_by=self.admin_user,
            final_score=Decimal('91.73'),
            final_grade='Z',
            attendance_percentage=Decimal('64.29'),
        )

        original_compression = rl_config.pageCompression
        rl_config.pageCompression = 0
        try:
            pdf_bytes = CertificatePDFGenerator(cert).generate_pdf()
        finally:
            rl_config.pageCompression = original_compression

        pdf_text = pdf_bytes.decode('latin-1', errors='ignore')

        self.assertIn('STUDENT USER', pdf_text)
        self.assertIn('Certificate No.', pdf_text)
        self.assertNotIn('91.73', pdf_text)
        self.assertNotIn('64.29', pdf_text)
        self.assertNotIn('Grade', pdf_text)
        self.assertNotIn('Attendance', pdf_text)

    def test_eligible_endpoint_reports_blocker_summary(self):
        self.client.force_authenticate(self.admin_user)

        response = self.client.get(reverse('certificate-eligible'), {'course_id': self.course.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['eligible_students'], [])
        self.assertEqual(response.data['summary']['examined'], 1)
        self.assertEqual(response.data['summary']['eligible'], 0)
        self.assertEqual(response.data['summary']['ineligible'], 1)
        self.assertIn(
            {
                'code': 'assessment_missing',
                'label': 'Assessment result not created',
                'count': 1,
            },
            response.data['summary']['blockers'],
        )

    def test_eligible_endpoint_reports_each_assessment_and_certificate_blocker(self):
        def create_enrollment(label, enrollment_status=Enrollment.STATUS_COMPLETED, payment_status=Payment.STATUS_PAID, student_status=Student.STATUS_APPROVED):
            student = Student.objects.create(
                first_name=label,
                last_name='Learner',
                email=f'{label.lower()}@test.com',
                learner_type=Student.LEARNER_ADULT,
                approval_status=student_status,
            )
            enrollment = Enrollment.objects.create(
                student=student,
                course=self.course,
                instructor=self.instructor,
                status=enrollment_status,
            )
            Payment.objects.create(
                enrollment=enrollment,
                amount=300.00,
                status=payment_status,
            )
            return enrollment

        active_enrollment = create_enrollment('Active', enrollment_status=Enrollment.STATUS_ACTIVE)
        AssessmentResult.objects.create(
            enrollment=active_enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
        )

        payment_enrollment = create_enrollment('Payment', payment_status=Payment.STATUS_PENDING)
        AssessmentResult.objects.create(
            enrollment=payment_enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
        )

        practical_missing = create_enrollment('PracticalMissing')
        AssessmentResult.objects.create(
            enrollment=practical_missing,
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
        )

        final_project_missing = create_enrollment('FinalProjectMissing')
        AssessmentResult.objects.create(
            enrollment=final_project_missing,
            practical_score=Decimal('35.00'),
            objective_quiz_score=Decimal('15.00'),
        )

        objective_missing = create_enrollment('ObjectiveMissing')
        AssessmentResult.objects.create(
            enrollment=objective_missing,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
        )

        unapproved = create_enrollment('Unapproved')
        AssessmentResult.objects.create(
            enrollment=unapproved,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
        )

        below_pass = create_enrollment('BelowPass')
        AssessmentResult.objects.create(
            enrollment=below_pass,
            practical_score=Decimal('20.00'),
            final_project_score=Decimal('20.00'),
            objective_quiz_score=Decimal('10.00'),
        )

        active_certificate = create_enrollment('ActiveCertificate')
        AssessmentResult.objects.create(
            enrollment=active_certificate,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
        )
        Certificate.objects.create(
            student=active_certificate.student,
            enrollment=active_certificate,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ACTIVE,
            issued_by=self.admin_user,
        )

        revoked_certificate = create_enrollment('RevokedCertificate')
        AssessmentResult.objects.create(
            enrollment=revoked_certificate,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
        )
        Certificate.objects.create(
            student=revoked_certificate.student,
            enrollment=revoked_certificate,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_REVOKED,
            issued_by=self.admin_user,
        )

        pending_student = create_enrollment('PendingStudent', student_status=Student.STATUS_PENDING)
        AssessmentResult.objects.create(
            enrollment=pending_student,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.admin_user,
            approved_at=timezone.now(),
        )

        self.client.force_authenticate(self.admin_user)
        response = self.client.get(reverse('certificate-eligible'), {'course_id': self.course.id})

        self.assertEqual(response.status_code, 200)
        blocker_codes = {item['code'] for item in response.data['summary']['blockers']}
        self.assertTrue({
            'assessment_missing',
            'enrollment_incomplete',
            'payment_outstanding',
            'practical_score_missing',
            'final_project_score_missing',
            'objective_quiz_score_missing',
            'result_awaiting_approval',
            'below_pass_mark',
            'certificate_already_issued',
            'certificate_revoked',
            'student_not_approved',
        }.issubset(blocker_codes))

    def test_instructor_eligible_endpoint_counts_only_assigned_enrollments(self):
        other_student = Student.objects.create(
            first_name='Other',
            last_name='Learner',
            email='other-scope@test.com',
            learner_type=Student.LEARNER_ADULT,
            approval_status=Student.STATUS_APPROVED,
        )
        Enrollment.objects.create(
            student=other_student,
            course=self.course,
            instructor=self.other_instructor,
            status=Enrollment.STATUS_COMPLETED,
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.get(reverse('certificate-eligible'), {'course_id': self.course.id})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['examined'], 1)

    def test_parent_sees_linked_child_results_only(self):
        self._create_approved_assessment_result()
        other_parent_user = User.objects.create_user(
            email='result-other-parent@test.com',
            password='testpass123',
            first_name='Other',
            last_name='Parent',
            role='parent',
            approval_status='approved',
        )
        other_parent = Parent.objects.create(
            user=other_parent_user,
            first_name='Other',
            last_name='Parent',
            email='result-other-parent-profile@test.com',
        )
        other_student = Student.objects.create(
            parent=other_parent,
            first_name='Other',
            last_name='Child',
            email='result-other-child@test.com',
            learner_type='child',
            approval_status='approved',
        )
        other_enrollment = Enrollment.objects.create(
            student=other_student,
            course=self.course,
            instructor=self.instructor,
            status='completed',
        )
        AssessmentResult.objects.create(
            enrollment=other_enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
        )
        self.client.force_authenticate(self.parent_user)

        response = self.client.get(reverse('my-assessment-results'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['student_id'], self.student.id)

    def test_adult_learner_sees_own_result_only(self):
        self._create_approved_assessment_result()
        self.client.force_authenticate(self.student_user)

        response = self.client.get(reverse('my-assessment-results'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['student_id'], self.student.id)

    def _response_bytes(self, response):
        if getattr(response, 'streaming', False):
            return b''.join(response.streaming_content)
        return response.content

    def _create_approved_assessment_result(self, enrollment=None, approved_by=None):
        return AssessmentResult.objects.create(
            enrollment=enrollment or self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=approved_by or self.admin_user,
            approved_at=timezone.now(),
        )

    def _create_certificate_with_file(self):
        cert = Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ISSUED,
            issued_by=self.admin_user,
            final_score=88,
            final_grade='A',
            attendance_percentage=100,
        )
        cert.certificate_file.save(
            f'{cert.certificate_number}.pdf',
            ContentFile(b'%PDF-1.4 certificate'),
            save=True,
        )
        return cert

    def _create_other_student_certificate_with_file(self):
        other_parent_user = User.objects.create_user(
            email='other-parent@test.com',
            password='testpass123',
            first_name='Other',
            last_name='Parent',
            role='parent',
            approval_status='approved',
        )
        other_parent = Parent.objects.create(
            user=other_parent_user,
            first_name='Other',
            last_name='Parent',
            email='other-parent-profile@test.com',
            phone_number='0244000000',
        )
        other_student_user = User.objects.create_user(
            email='other-student@test.com',
            password='testpass123',
            first_name='Other',
            last_name='Student',
            role='student',
            approval_status='approved',
        )
        other_student = Student.objects.create(
            user=other_student_user,
            parent=other_parent,
            first_name='Other',
            last_name='Student',
            email='other-student-profile@test.com',
            learner_type='child',
            approval_status='approved',
        )
        other_enrollment = Enrollment.objects.create(
            student=other_student,
            course=self.course,
            instructor=self.instructor,
            status='completed',
        )
        Payment.objects.create(
            enrollment=other_enrollment,
            amount=300.00,
            status='paid',
        )
        cert = Certificate.objects.create(
            student=other_student,
            enrollment=other_enrollment,
            course=self.course,
            completion_date=date.today(),
            status=Certificate.STATUS_ISSUED,
            issued_by=self.admin_user,
        )
        cert.certificate_file.save(
            f'{cert.certificate_number}.pdf',
            ContentFile(b'%PDF-1.4 certificate'),
            save=True,
        )
        return cert
