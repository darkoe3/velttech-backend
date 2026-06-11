from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from courses.models import Course
from students.models import Parent, Student

from .models import Assignment, AssignmentSubmission, Enrollment


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False)
class InstructorGradingTests(APITestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='instructor@example.com',
            password='pass',
            first_name='Ada',
            last_name='Tutor',
            role=User.ROLE_INSTRUCTOR,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.other_instructor = User.objects.create_user(
            email='other@example.com',
            password='pass',
            first_name='Other',
            last_name='Tutor',
            role=User.ROLE_INSTRUCTOR,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.parent_user = User.objects.create_user(
            email='parent@example.com',
            password='pass',
            first_name='Pat',
            last_name='Parent',
            role=User.ROLE_PARENT,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.student_user = User.objects.create_user(
            email='student@example.com',
            password='pass',
            first_name='Sam',
            last_name='Student',
            role=User.ROLE_STUDENT,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.parent = Parent.objects.create(
            user=self.parent_user,
            first_name='Pat',
            last_name='Parent',
            email='parent-profile@example.com',
            phone_number='233555000111',
        )
        self.student = Student.objects.create(
            user=self.student_user,
            parent=self.parent,
            first_name='Sam',
            last_name='Student',
            email='student-profile@example.com',
            learner_type=Student.LEARNER_CHILD,
            approval_status=Student.STATUS_APPROVED,
        )
        self.course = Course.objects.create(
            title='Python Programming',
            description='Learn Python',
            duration_months=3,
            monthly_fee=100,
            fee=300,
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course,
            instructor=self.instructor,
            status=Enrollment.STATUS_ACTIVE,
        )
        self.assignment = Assignment.objects.create(
            title='Loops',
            description='Solve loop exercises.',
            course=self.course,
            instructor=self.instructor,
            due_date='2026-07-01',
            submission_type=Assignment.SUBMISSION_TEXT,
            marks=50,
        )
        self.submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student,
            text_answer='for item in items: print(item)',
            submission_text='for item in items: print(item)',
            status=AssignmentSubmission.STATUS_SUBMITTED,
            max_score=50,
        )

    def grade_url(self):
        return reverse('instructor-grade-submission', args=[self.submission.id])

    def test_instructor_can_grade_assigned_submission(self):
        self.client.force_authenticate(self.instructor)
        response = self.client.patch(
            self.grade_url(),
            {
                'grade': 45,
                'feedback': 'Good work. Improve your comments.',
                'status': 'graded',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.score, 45)
        self.assertEqual(self.submission.status, AssignmentSubmission.STATUS_GRADED)
        self.assertEqual(self.submission.graded_by, self.instructor)
        self.assertIsNotNone(self.submission.graded_at)
        self.assertEqual(response.data['grade'], 45)
        self.assertEqual(response.data['max_score'], 50)

    def test_grade_cannot_exceed_max_score(self):
        self.client.force_authenticate(self.instructor)
        response = self.client.patch(
            self.grade_url(),
            {
                'grade': 80,
                'feedback': 'Too high.',
                'status': 'graded',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unassigned_instructor_cannot_grade_submission(self):
        self.client.force_authenticate(self.other_instructor)
        response = self.client.patch(
            self.grade_url(),
            {
                'grade': 40,
                'feedback': 'Looks fine.',
                'status': 'graded',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_parent_cannot_grade_submission(self):
        self.client.force_authenticate(self.parent_user)
        response = self.client.patch(
            self.grade_url(),
            {
                'grade': 40,
                'feedback': 'Parent attempt.',
                'status': 'graded',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
