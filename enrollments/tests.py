from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from courses.models import Course
from students.models import Parent, Student

from .models import Assignment, AssignmentQuestion, AssignmentSubmission, Enrollment


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False, MIDDLEWARE=[])
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
        self.admin = User.objects.create_user(
            email='admin@example.com',
            password='pass',
            first_name='Admin',
            last_name='User',
            role=User.ROLE_ADMIN,
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
            submission_type=Assignment.ASSESSMENT_PRACTICAL,
            marks=50,
        )
        self.submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=self.student,
            status=AssignmentSubmission.STATUS_SUBMITTED,
            max_score=50,
        )

    def grade_url(self):
        return reverse('instructor-grade-submission', args=[self.submission.id])

    def assignment_list_url(self):
        return reverse('instructor-assignments')

    def assignment_detail_url(self, assignment):
        return reverse('instructor-assignment-detail', args=[assignment.id])

    def submit_url(self, assignment):
        return reverse('submit_assignment', args=[assignment.id])

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

    def test_instructor_creates_quiz_and_student_receives_auto_marked_result(self):
        self.client.force_authenticate(self.instructor)
        create_response = self.client.post(
            self.assignment_list_url(),
            {
                'title': 'Quiz Task',
                'description': 'Choose the correct answers.',
                'course': self.course.id,
                'due_date': '2026-08-01',
                'submission_type': Assignment.ASSESSMENT_QUIZ,
                'marks': 20,
                'questions': [
                    {
                        'question_text': 'Which keyword starts a Python loop?',
                        'option_a': 'for',
                        'option_b': 'make',
                        'option_c': 'class',
                        'option_d': 'return',
                        'correct_answer': 'A',
                        'marks': 10,
                    },
                    {
                        'question_text': 'Which keyword exits a loop early?',
                        'option_a': 'skip',
                        'option_b': 'break',
                        'option_c': 'stop',
                        'option_d': 'end',
                        'correct_answer': 'B',
                        'marks': 10,
                    },
                ],
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        assignment = Assignment.objects.get(id=create_response.data['id'])
        self.assertEqual(assignment.submission_type, Assignment.ASSESSMENT_QUIZ)
        self.assertEqual(assignment.questions.count(), 2)

        self.client.force_authenticate(self.student_user)
        question_ids = list(assignment.questions.values_list('id', flat=True))
        submit_response = self.client.post(
            self.submit_url(assignment),
            {
                'answers': {
                    str(question_ids[0]): 'A',
                    str(question_ids[1]): 'C',
                }
            },
            format='json',
        )

        self.assertEqual(submit_response.status_code, status.HTTP_200_OK)
        self.assertEqual(submit_response.data['score'], 10)
        self.assertEqual(submit_response.data['max_score'], 20)
        self.assertEqual(submit_response.data['status'], AssignmentSubmission.STATUS_GRADED)
        self.assertEqual(submit_response.data['feedback'], 'Auto-marked: 1/2 correct.')
        self.assertEqual(submit_response.data['quiz_answers'][str(question_ids[0])], 'A')

    def test_quiz_requires_answers_for_all_questions(self):
        assignment = Assignment.objects.create(
            title='Quiz Required',
            description='Answer all questions.',
            course=self.course,
            instructor=self.instructor,
            due_date='2026-08-02',
            submission_type=Assignment.ASSESSMENT_QUIZ,
            marks=10,
        )
        question = AssignmentQuestion.objects.create(
            assignment=assignment,
            question_text='Pick A.',
            option_a='A',
            option_b='B',
            option_c='C',
            option_d='D',
            correct_answer='A',
            marks=10,
        )
        self.client.force_authenticate(self.student_user)

        response = self.client.post(
            self.submit_url(assignment),
            {'answers': {str(question.id): ''}},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_cannot_submit_practical_assessment(self):
        assignment = Assignment.objects.create(
            title='Practical Task',
            description='Instructor observes and grades.',
            course=self.course,
            instructor=self.instructor,
            due_date='2026-08-03',
            submission_type=Assignment.ASSESSMENT_PRACTICAL,
            marks=40,
        )
        self.client.force_authenticate(self.student_user)

        response = self.client.post(
            self.submit_url(assignment),
            {'answers': {}},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Practical assessments are graded directly', response.data['detail'])

    def test_instructor_grades_practical_assessment_for_enrolled_student(self):
        assignment = Assignment.objects.create(
            title='Practical Grade',
            description='Build a small app.',
            course=self.course,
            instructor=self.instructor,
            due_date='2026-08-04',
            submission_type=Assignment.ASSESSMENT_PRACTICAL,
            marks=30,
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.post(
            reverse('instructor-practical-grade', args=[assignment.id]),
            {
                'student_id': self.student.id,
                'score': 27,
                'feedback': 'Strong implementation.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['score'], 27)
        self.assertEqual(response.data['max_score'], 30)
        self.assertEqual(response.data['feedback'], 'Strong implementation.')
        submission = AssignmentSubmission.objects.get(assignment=assignment, student=self.student)
        self.assertEqual(submission.status, AssignmentSubmission.STATUS_GRADED)
        self.assertEqual(submission.graded_by, self.instructor)

    def test_instructor_cannot_grade_practical_above_max_score(self):
        assignment = Assignment.objects.create(
            title='Practical Max',
            description='Build a page.',
            course=self.course,
            instructor=self.instructor,
            due_date='2026-08-05',
            submission_type=Assignment.ASSESSMENT_PRACTICAL,
            marks=10,
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.post(
            reverse('instructor-practical-grade', args=[assignment.id]),
            {'student_id': self.student.id, 'score': 11, 'feedback': 'Too high.'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_instructor_edits_assignment(self):
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assignment_detail_url(self.assignment),
            {
                'title': 'Loops Updated',
                'description': 'Updated instructions.',
                'course': self.course.id,
                'due_date': '2026-07-10',
                'submission_type': Assignment.ASSESSMENT_PRACTICAL,
                'marks': 60,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.title, 'Loops Updated')
        self.assertEqual(self.assignment.submission_type, Assignment.ASSESSMENT_PRACTICAL)

    def test_instructor_deletes_assignment(self):
        assignment = Assignment.objects.create(
            title='Delete Me',
            description='Temporary.',
            course=self.course,
            instructor=self.instructor,
            due_date='2026-08-06',
            submission_type=Assignment.ASSESSMENT_PRACTICAL,
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.delete(self.assignment_detail_url(assignment))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Assignment.objects.filter(id=assignment.id).exists())

    def test_unauthorized_users_cannot_edit_or_delete_assignments(self):
        self.client.force_authenticate(self.other_instructor)
        other_response = self.client.patch(
            self.assignment_detail_url(self.assignment),
            {'title': 'Not allowed'},
            format='json',
        )
        self.assertEqual(other_response.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(self.student_user)
        student_response = self.client.delete(self.assignment_detail_url(self.assignment))
        self.assertEqual(student_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_edit_any_assignment(self):
        self.client.force_authenticate(self.admin)

        response = self.client.patch(
            self.assignment_detail_url(self.assignment),
            {'title': 'Admin Updated'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.title, 'Admin Updated')
