from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from courses.models import Course
from enrollments.models import Attendance, Enrollment, LessonNote, ProgressReport
from students.models import Parent, Student


User = get_user_model()


PASSWORD_RESET_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'password-reset-rate-limit-tests',
    }
}


@override_settings(CACHES=PASSWORD_RESET_CACHE, SECURE_SSL_REDIRECT=False)
class PasswordResetRateLimitTests(APITestCase):
    def password_reset_url(self):
        return reverse('password-reset-request')

    def test_password_reset_is_limited_by_email(self):
        for index in range(5):
            response = self.client.post(
                self.password_reset_url(),
                {'email': 'learner@example.com'},
                format='json',
                REMOTE_ADDR=f'10.0.0.{index}',
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            self.password_reset_url(),
            {'email': 'learner@example.com'},
            format='json',
            REMOTE_ADDR='10.0.0.99',
        )

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_password_reset_is_limited_by_ip(self):
        for index in range(5):
            response = self.client.post(
                self.password_reset_url(),
                {'email': f'learner-{index}@example.com'},
                format='json',
                REMOTE_ADDR='10.0.1.1',
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.post(
            self.password_reset_url(),
            {'email': 'another-learner@example.com'},
            format='json',
            REMOTE_ADDR='10.0.1.1',
        )

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


@override_settings(SECURE_SSL_REDIRECT=False)
class AdminInstructorPortalAccessTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            email='admin@example.com',
            password='pass',
            role=User.ROLE_ADMIN,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            password='pass',
            role=User.ROLE_INSTRUCTOR,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.parent_user = User.objects.create_user(
            email='parent@example.com',
            password='pass',
            role=User.ROLE_PARENT,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.student_user = User.objects.create_user(
            email='student@example.com',
            password='pass',
            role=User.ROLE_STUDENT,
            approval_status=User.APPROVAL_APPROVED,
        )
        parent = Parent.objects.create(
            user=self.parent_user,
            first_name='Pat',
            last_name='Parent',
            email='parent-profile@example.com',
            phone_number='233555000111',
        )
        student = Student.objects.create(
            user=self.student_user,
            parent=parent,
            first_name='Sam',
            last_name='Student',
            email='student-profile@example.com',
            approval_status=Student.STATUS_APPROVED,
        )
        course = Course.objects.create(
            title='Python Programming',
            description='Learn Python',
            duration_months=3,
            monthly_fee=100,
            fee=300,
        )
        self.enrollment = Enrollment.objects.create(
            student=student,
            course=course,
            instructor=self.instructor,
            status=Enrollment.STATUS_ACTIVE,
        )
        Attendance.objects.create(
            enrollment=self.enrollment,
            date='2026-06-01',
            status=Attendance.STATUS_PRESENT,
            recorded_by=self.instructor,
        )
        LessonNote.objects.create(
            instructor=self.instructor,
            course=course,
            title='Loops',
            content='Loop lesson notes.',
            lesson_date='2026-06-01',
        )
        ProgressReport.objects.create(
            enrollment=self.enrollment,
            progress_score=80,
            created_by=self.instructor,
        )

    def test_admin_can_access_instructor_portal_data_endpoints(self):
        self.client.force_authenticate(self.admin)
        endpoint_names = [
            'instructor-courses',
            'instructor-enrollments',
            'instructor-attendance',
            'instructor-lesson-notes',
            'instructor-progress-reports',
            'instructor-assignments',
        ]

        for endpoint_name in endpoint_names:
            with self.subTest(endpoint_name=endpoint_name):
                response = self.client.get(reverse(endpoint_name))
                self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_admin_can_create_instructor_portal_records(self):
        self.client.force_authenticate(self.admin)

        attendance_response = self.client.post(
            reverse('instructor-attendance'),
            {
                'enrollment': self.enrollment.id,
                'date': '2026-06-02',
                'status': Attendance.STATUS_LATE,
                'remarks': 'Admin recorded.',
            },
            format='json',
        )
        self.assertEqual(attendance_response.status_code, status.HTTP_201_CREATED)

        progress_response = self.client.post(
            reverse('instructor-progress-reports'),
            {
                'enrollment': self.enrollment.id,
                'progress_score': 85,
                'strengths': 'Good progress.',
                'areas_for_improvement': 'Practice more.',
                'instructor_comment': 'Admin recorded.',
            },
            format='json',
        )
        self.assertEqual(progress_response.status_code, status.HTTP_201_CREATED)
