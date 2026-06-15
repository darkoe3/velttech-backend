from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from datetime import date
from unittest.mock import patch

from rest_framework.test import APIClient

from courses.models import Course
from students.models import Student, Parent
from enrollments.models import Assignment, AssignmentSubmission, Attendance, Enrollment
from payments.models import Payment
from users.models import ActivityLog
from notifications.models import Notification
from .models import Certificate

User = get_user_model()


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
        """Test that certificate numbers are unique"""
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
        self.client.force_authenticate(self.other_instructor)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 403)

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_duplicate_certificate_is_blocked(self, generator_cls):
        generator_cls.return_value.save_to_certificate.return_value = None
        self.client.force_authenticate(self.admin_user)
        payload = {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }

        first = self.client.post(reverse('certificate-issue'), payload, format='json')
        second = self.client.post(reverse('certificate-issue'), payload, format='json')

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)

    def test_student_downloads_own_certificate(self):
        cert = self._create_certificate_with_file()
        self.client.force_authenticate(self.student_user)

        response = self.client.get(reverse('certificate-download', args=[cert.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(ActivityLog.objects.filter(action='Certificate downloaded').exists())

    def test_parent_downloads_child_certificate(self):
        cert = self._create_certificate_with_file()
        self.client.force_authenticate(self.parent_user)

        response = self.client.get(reverse('certificate-download', args=[cert.id]))

        self.assertEqual(response.status_code, 200)

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
        self.assertEqual(response.data['final_score'], '85.00')
        self.assertEqual(response.data['final_grade'], 'A')
        self.assertEqual(response.data['attendance_percentage'], '50.00')

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
