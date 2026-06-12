from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from datetime import date
from unittest.mock import patch

from rest_framework.test import APIClient

from courses.models import Course
from students.models import Student, Parent
from enrollments.models import Assignment, AssignmentSubmission, Attendance, Enrollment
from payments.models import Payment
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
        self.assertTrue(cert.certificate_number.startswith('VTA-CERT-'))
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


@override_settings(MIDDLEWARE=[])
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
        self.assertEqual(response.data['status'], Certificate.STATUS_ISSUED)
        self.assertEqual(response.data['certificate_type'], Certificate.TYPE_EXCELLENCE)
        self.assertEqual(response.data['final_grade'], 'A')
        self.assertEqual(Certificate.objects.count(), 1)

    @patch('certificates.pdf_generator.CertificatePDFGenerator')
    def test_instructor_can_only_issue_assigned_certificate(self, generator_cls):
        generator_cls.return_value.save_to_certificate.return_value = None
        self.client.force_authenticate(self.other_instructor)

        response = self.client.post(reverse('certificate-issue'), {
            'enrollment_id': self.enrollment.id,
            'completion_date': date.today().isoformat(),
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('assigned learners', str(response.data))

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

    def test_parent_downloads_child_certificate(self):
        cert = self._create_certificate_with_file()
        self.client.force_authenticate(self.parent_user)

        response = self.client.get(reverse('certificate-download', args=[cert.id]))

        self.assertEqual(response.status_code, 200)

    def test_public_verification_and_revoked_status(self):
        cert = self._create_certificate_with_file()
        cert.revoke('Administrative correction')

        response = self.client.get(reverse('certificate-verify', args=[cert.verification_code]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], Certificate.STATUS_REVOKED)
        self.assertEqual(response.data['status_label'], 'Revoked')
        self.assertEqual(response.data['certificate_number'], cert.certificate_number)

    def test_public_verification_by_certificate_number(self):
        cert = self._create_certificate_with_file()

        response = self.client.get(reverse('certificate-verify', args=[cert.certificate_number]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['certificate_number'], cert.certificate_number)
        self.assertEqual(response.data['student_name'], 'Student User')
        self.assertEqual(response.data['course_title'], self.course.title)
        self.assertEqual(response.data['status_label'], 'Valid')

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
