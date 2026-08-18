import uuid
from io import StringIO
from decimal import Decimal

from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from courses.models import Course
from certificates.models import Certificate
from certificates.services import check_combined_result_certificate_eligibility
from payments.models import Payment
from students.models import Parent, Student

from .models import Assignment, AssignmentQuestion, AssignmentSubmission, AssessmentResult, Enrollment, LearningResource


User = get_user_model()


@override_settings(SECURE_SSL_REDIRECT=False, MIDDLEWARE=[])
class LearningResourceAPITests(APITestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='resource-instructor@example.com',
            password='pass',
            first_name='Resource',
            last_name='Tutor',
            role=User.ROLE_INSTRUCTOR,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.other_instructor = User.objects.create_user(
            email='other-resource-instructor@example.com',
            password='pass',
            first_name='Other',
            last_name='Tutor',
            role=User.ROLE_INSTRUCTOR,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.admin = User.objects.create_user(
            email='resource-admin@example.com',
            password='pass',
            first_name='Admin',
            last_name='User',
            role=User.ROLE_ADMIN,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.parent_user = User.objects.create_user(
            email='resource-parent@example.com',
            password='pass',
            first_name='Parent',
            last_name='User',
            role=User.ROLE_PARENT,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.other_parent_user = User.objects.create_user(
            email='other-resource-parent@example.com',
            password='pass',
            first_name='Other',
            last_name='Parent',
            role=User.ROLE_PARENT,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.adult_user = User.objects.create_user(
            email='resource-adult@example.com',
            password='pass',
            first_name='Adult',
            last_name='Learner',
            role=User.ROLE_STUDENT,
            account_type=User.ACCOUNT_ADULT_LEARNER,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.parent = Parent.objects.create(
            user=self.parent_user,
            first_name='Parent',
            last_name='User',
            email='resource-parent-profile@example.com',
            phone_number='233555000001',
        )
        self.other_parent = Parent.objects.create(
            user=self.other_parent_user,
            first_name='Other',
            last_name='Parent',
            email='other-resource-parent-profile@example.com',
            phone_number='233555000002',
        )
        self.student = Student.objects.create(
            parent=self.parent,
            first_name='Child',
            last_name='Learner',
            email='resource-child@example.com',
            learner_type=Student.LEARNER_CHILD,
            approval_status=Student.STATUS_APPROVED,
        )
        self.other_student = Student.objects.create(
            parent=self.other_parent,
            first_name='Other',
            last_name='Learner',
            email='other-resource-child@example.com',
            learner_type=Student.LEARNER_CHILD,
            approval_status=Student.STATUS_APPROVED,
        )
        self.adult_student = Student.objects.create(
            user=self.adult_user,
            first_name='Adult',
            last_name='Learner',
            email='resource-adult-profile@example.com',
            learner_type=Student.LEARNER_ADULT,
            approval_status=Student.STATUS_APPROVED,
        )
        self.course = Course.objects.create(
            title='AI-Assisted Development',
            description='Build with AI',
            duration_months=2,
            monthly_fee=100,
            fee=200,
        )
        self.other_course = Course.objects.create(
            title='Unassigned Course',
            description='Other course',
            duration_months=1,
            monthly_fee=100,
            fee=100,
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course,
            instructor=self.instructor,
            status=Enrollment.STATUS_ACTIVE,
        )
        self.adult_enrollment = Enrollment.objects.create(
            student=self.adult_student,
            course=self.course,
            instructor=self.instructor,
            status=Enrollment.STATUS_ACTIVE,
        )
        self.other_enrollment = Enrollment.objects.create(
            student=self.other_student,
            course=self.other_course,
            instructor=self.other_instructor,
            status=Enrollment.STATUS_ACTIVE,
        )

    def list_url(self):
        return reverse('instructor-resources')

    def detail_url(self, resource):
        return reverse('instructor-resource-detail', args=[resource.id])

    def my_url(self):
        return reverse('my-resources')

    def payload(self, **overrides):
        data = {
            'title': 'Prompt Engineering Guide',
            'description': 'Read before class.',
            'resource_type': LearningResource.RESOURCE_DOCUMENT,
            'url': 'https://drive.google.com/example',
            'course': self.course.id,
            'target_student': None,
            'is_published': True,
        }
        data.update(overrides)
        return data

    def create_resource(self, **overrides):
        data = self.payload(**overrides)
        data['course'] = Course.objects.get(pk=data['course'])
        target_student = data.get('target_student')
        if target_student:
            data['target_student'] = Student.objects.get(pk=target_student)
        return LearningResource.objects.create(instructor=self.instructor, **data)

    def test_instructor_creates_course_resource(self):
        self.client.force_authenticate(self.instructor)
        response = self.client.post(self.list_url(), self.payload(), format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        resource = LearningResource.objects.get(pk=response.data['id'])
        self.assertEqual(resource.instructor, self.instructor)
        self.assertIsNone(resource.target_student)
        self.assertIsNotNone(resource.published_at)

    def test_instructor_creates_individual_learner_resource(self):
        self.client.force_authenticate(self.instructor)
        response = self.client.post(
            self.list_url(),
            self.payload(target_student=self.student.id),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['target_student'], self.student.id)

    def test_instructor_cannot_use_unassigned_course(self):
        self.client.force_authenticate(self.instructor)
        response = self.client.post(
            self.list_url(),
            self.payload(course=self.other_course.id),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_instructor_cannot_target_learner_outside_course(self):
        self.client.force_authenticate(self.instructor)
        response = self.client.post(
            self.list_url(),
            self.payload(target_student=self.other_student.id),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_instructor_sees_own_resources_only(self):
        own = self.create_resource(title='Own')
        LearningResource.objects.create(
            title='Other',
            description='Other resource',
            resource_type=LearningResource.RESOURCE_WEBSITE,
            url='https://example.com/other',
            course=self.other_course,
            instructor=self.other_instructor,
            is_published=True,
        )
        self.client.force_authenticate(self.instructor)
        response = self.client.get(self.list_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in response.data], [own.id])

    def test_admin_sees_all_resources(self):
        own = self.create_resource(title='Own')
        other = LearningResource.objects.create(
            title='Other',
            description='Other resource',
            resource_type=LearningResource.RESOURCE_WEBSITE,
            url='https://example.com/other',
            course=self.other_course,
            instructor=self.other_instructor,
            is_published=True,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get(self.list_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({item['id'] for item in response.data}, {own.id, other.id})

    def test_parent_sees_published_resource_for_linked_child(self):
        resource = self.create_resource()
        self.client.force_authenticate(self.parent_user)
        response = self.client.get(self.my_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in response.data], [resource.id])

    def test_parent_cannot_see_unrelated_child_resource(self):
        LearningResource.objects.create(
            title='Private',
            description='Private note',
            resource_type=LearningResource.RESOURCE_NOTE,
            course=self.other_course,
            instructor=self.other_instructor,
            target_student=self.other_student,
            is_published=True,
        )
        self.client.force_authenticate(self.parent_user)
        response = self.client.get(self.my_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_adult_learner_sees_own_resource(self):
        resource = self.create_resource(target_student=self.adult_student.id)
        self.client.force_authenticate(self.adult_user)
        response = self.client.get(self.my_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([item['id'] for item in response.data], [resource.id])

    def test_unpublished_resource_hidden_from_learner(self):
        self.create_resource(is_published=False)
        self.client.force_authenticate(self.parent_user)
        response = self.client.get(self.my_url())
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_note_resource_works_without_url(self):
        self.client.force_authenticate(self.instructor)
        response = self.client.post(
            self.list_url(),
            self.payload(
                resource_type=LearningResource.RESOURCE_NOTE,
                url='',
                description='Bring your laptop.',
            ),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_non_note_requires_url(self):
        self.client.force_authenticate(self.instructor)
        response = self.client.post(self.list_url(), self.payload(url=''), format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('url', response.data)

    def test_invalid_url_rejected(self):
        self.client.force_authenticate(self.instructor)
        response = self.client.post(
            self.list_url(),
            self.payload(url='javascript:alert(1)'),
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('url', response.data)

    def test_delete_update_authorization(self):
        resource = self.create_resource()
        self.client.force_authenticate(self.other_instructor)
        patch_response = self.client.patch(
            self.detail_url(resource),
            {'title': 'Changed'},
            format='json',
        )
        delete_response = self.client.delete(self.detail_url(resource))
        self.assertEqual(patch_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(delete_response.status_code, status.HTTP_404_NOT_FOUND)
        resource.refresh_from_db()
        self.assertEqual(resource.title, 'Prompt Engineering Guide')

        self.client.force_authenticate(self.instructor)
        patch_response = self.client.patch(
            self.detail_url(resource),
            {'title': 'Changed'},
            format='json',
        )
        self.assertEqual(patch_response.status_code, status.HTTP_200_OK)
        delete_response = self.client.delete(self.detail_url(resource))
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)


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

    def generate_link_url(self, assignment):
        return reverse('instructor-assessment-generate-link', args=[assignment.id])

    def sharing_url(self, assignment):
        return reverse('instructor-assessment-sharing', args=[assignment.id])

    def public_assessment_url(self, assignment):
        return reverse('public-assessment', args=[assignment.share_token])

    def create_student_for_other_instructor(self):
        student_user = User.objects.create_user(
            email='other-student@example.com',
            password='pass',
            first_name='Una',
            last_name='Assigned',
            role=User.ROLE_STUDENT,
            approval_status=User.APPROVAL_APPROVED,
        )
        student = Student.objects.create(
            user=student_user,
            parent=self.parent,
            first_name='Una',
            last_name='Assigned',
            email='other-student-profile@example.com',
            learner_type=Student.LEARNER_CHILD,
            approval_status=Student.STATUS_APPROVED,
        )
        Enrollment.objects.create(
            student=student,
            course=self.course,
            instructor=self.other_instructor,
            status=Enrollment.STATUS_ACTIVE,
        )
        return student

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
        self.assertEqual(response.data['percentage'], 90.0)
        self.assertEqual(response.data['letter_grade'], 'A')

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

    def test_instructor_cannot_create_targeted_assignment_for_unassigned_student(self):
        unassigned_student = self.create_student_for_other_instructor()
        self.client.force_authenticate(self.instructor)

        response = self.client.post(
            self.assignment_list_url(),
            {
                'title': 'Wrong Learner',
                'description': 'This should not be allowed.',
                'course': self.course.id,
                'target_student': unassigned_student.id,
                'due_date': '2026-08-01',
                'submission_type': Assignment.ASSESSMENT_PRACTICAL,
                'marks': 20,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Assignment.objects.filter(title='Wrong Learner').exists())

    def test_instructor_cannot_grade_submission_for_unassigned_student(self):
        unassigned_student = self.create_student_for_other_instructor()
        submission = AssignmentSubmission.objects.create(
            assignment=self.assignment,
            student=unassigned_student,
            status=AssignmentSubmission.STATUS_SUBMITTED,
            max_score=50,
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            reverse('instructor-grade-submission', args=[submission.id]),
            {
                'grade': 40,
                'feedback': 'Wrong instructor.',
                'status': 'graded',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        submission.refresh_from_db()
        self.assertIsNone(submission.score)
        self.assertIsNone(submission.graded_by)

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
        self.assertEqual(submit_response.data['percentage'], 50.0)
        self.assertEqual(submit_response.data['letter_grade'], 'D')
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

    def test_student_assignment_payload_includes_answerable_questions_without_answers(self):
        assignment = Assignment.objects.create(
            title='Visible Quiz',
            description='Answer all visible questions.',
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

        response = self.client.get(reverse('my_assignments'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = next(item for item in response.data if item['id'] == assignment.id)
        self.assertEqual(payload['questions'][0]['id'], question.id)
        self.assertNotIn('correct_answer', payload['questions'][0])
        self.assertIsNone(payload['submission'])

    def test_parent_cannot_submit_child_quiz(self):
        assignment = Assignment.objects.create(
            title='Child Quiz',
            description='Parent must not submit.',
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
        self.client.force_authenticate(self.parent_user)

        response = self.client.post(
            self.submit_url(assignment),
            {'answers': {str(question.id): 'A'}},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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
        self.assertEqual(response.data['percentage'], 90.0)
        self.assertEqual(response.data['letter_grade'], 'A')
        self.assertEqual(response.data['feedback'], 'Strong implementation.')
        submission = AssignmentSubmission.objects.get(assignment=assignment, student=self.student)
        self.assertEqual(submission.status, AssignmentSubmission.STATUS_GRADED)
        self.assertEqual(submission.graded_by, self.instructor)

    def test_instructor_submission_list_can_filter_by_assignment(self):
        other_assignment = Assignment.objects.create(
            title='Other Result',
            description='Different assessment.',
            course=self.course,
            instructor=self.instructor,
            due_date='2026-08-04',
            submission_type=Assignment.ASSESSMENT_PRACTICAL,
            marks=30,
        )
        AssignmentSubmission.objects.create(
            assignment=other_assignment,
            student=self.student,
            status=AssignmentSubmission.STATUS_GRADED,
            max_score=30,
            score=20,
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.get(reverse('instructor-submissions'), {'assignment': self.assignment.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['assignment'], self.assignment.id)

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

    def test_instructor_cannot_grade_practical_for_unassigned_student(self):
        unassigned_student = self.create_student_for_other_instructor()
        assignment = Assignment.objects.create(
            title='Practical Wrong Learner',
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
            {'student_id': unassigned_student.id, 'score': 8, 'feedback': 'Wrong instructor.'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(
            AssignmentSubmission.objects.filter(
                assignment=assignment,
                student=unassigned_student,
            ).exists()
        )

    def test_assignment_submission_letter_grade_scale(self):
        expectations = [
            (80, 'A'),
            (70, 'B'),
            (60, 'C'),
            (50, 'D'),
            (49, 'F'),
        ]
        for score, expected_grade in expectations:
            with self.subTest(score=score):
                self.submission.score = score
                self.submission.max_score = 100
                self.assignment.marks = 100
                self.assertEqual(self.submission.percentage, float(score))
                self.assertEqual(self.submission.letter_grade, expected_grade)

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

    def test_instructor_can_generate_public_assessment_token(self):
        self.client.force_authenticate(self.instructor)

        response = self.client.post(self.generate_link_url(self.assignment))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_public)
        self.assertEqual(response.data['token'], str(self.assignment.share_token))
        self.assertIn(f'/assessment/{self.assignment.share_token}', response.data['share_url'])
        self.assertIsNone(response.data['expires_at'])

    def test_instructor_can_update_assessment_sharing_settings(self):
        self.client.force_authenticate(self.instructor)
        expires_at = timezone.now() + timezone.timedelta(days=3)

        response = self.client.patch(
            self.sharing_url(self.assignment),
            {
                'is_public': True,
                'share_expires_at': expires_at.isoformat(),
                'max_guest_attempts': 2,
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assignment.refresh_from_db()
        self.assertTrue(self.assignment.is_public)
        self.assertEqual(self.assignment.max_guest_attempts, 2)
        self.assertIsNotNone(self.assignment.share_expires_at)

    def test_public_assessment_endpoint_returns_safe_metadata_only(self):
        self.assignment.is_public = True
        self.assignment.save(update_fields=['is_public'])
        AssignmentQuestion.objects.create(
            assignment=self.assignment,
            question_text='Hidden question.',
            option_a='A',
            option_b='B',
            option_c='C',
            option_d='D',
            correct_answer='A',
            marks=5,
        )

        response = self.client.get(self.public_assessment_url(self.assignment))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], self.assignment.title)
        self.assertEqual(response.data['course'], self.course.title)
        self.assertEqual(response.data['duration'], self.course.duration_months)
        self.assertEqual(response.data['instructions'], self.assignment.description)
        self.assertEqual(response.data['question_count'], 1)
        self.assertEqual(response.data['end_date'], self.assignment.due_date)
        self.assertEqual(response.data['academy_name'], 'Velttech Academy')
        self.assertNotIn('questions', response.data)
        self.assertNotIn('answers', response.data)
        self.assertNotIn('correct_answer', response.data)
        self.assertNotIn('marks', response.data)

    def test_public_assessment_rejects_expired_link(self):
        self.assignment.is_public = True
        self.assignment.share_expires_at = timezone.now() - timezone.timedelta(minutes=1)
        self.assignment.save(update_fields=['is_public', 'share_expires_at'])

        response = self.client.get(self.public_assessment_url(self.assignment))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_public_assessment_rejects_private_assessment(self):
        response = self.client.get(self.public_assessment_url(self.assignment))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_other_instructor_cannot_manage_assessment_sharing(self):
        self.client.force_authenticate(self.other_instructor)

        generate_response = self.client.post(self.generate_link_url(self.assignment))
        sharing_response = self.client.patch(
            self.sharing_url(self.assignment),
            {'is_public': True},
            format='json',
        )

        self.assertEqual(generate_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(sharing_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_assessment_rejects_invalid_token(self):
        response = self.client.get(reverse('public-assessment', args=[uuid.uuid4()]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_public_assessment_rejects_draft_assessment(self):
        self.assignment.is_public = True
        self.assignment.is_active = False
        self.assignment.save(update_fields=['is_public', 'is_active'])

        response = self.client.get(self.public_assessment_url(self.assignment))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


@override_settings(SECURE_SSL_REDIRECT=False, MIDDLEWARE=[])
class ReconcileAssessmentResultsCommandTests(APITestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='reconcile-instructor@example.com',
            password='pass',
            first_name='Recon',
            last_name='Tutor',
            role=User.ROLE_INSTRUCTOR,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.student = Student.objects.create(
            first_name='Historical',
            last_name='Learner',
            email='historical-learner@example.com',
            learner_type=Student.LEARNER_ADULT,
            approval_status=Student.STATUS_APPROVED,
        )
        self.course = Course.objects.create(
            title='Historical Assessment Course',
            description='Course with older enrollments',
            duration_months=2,
            monthly_fee=100,
            fee=200,
            certificate_pass_mark=Decimal('70.00'),
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course,
            instructor=self.instructor,
            status=Enrollment.STATUS_COMPLETED,
        )
        Payment.objects.create(
            enrollment=self.enrollment,
            amount=200,
            status=Payment.STATUS_PAID,
        )

    def run_command(self):
        output = StringIO()
        call_command('reconcile_assessment_results', stdout=output)
        return output.getvalue()

    def test_missing_result_is_created_incomplete_and_unapproved(self):
        output = self.run_command()

        result = AssessmentResult.objects.get(enrollment=self.enrollment)
        self.assertEqual(result.status, AssessmentResult.STATUS_INCOMPLETE)
        self.assertFalse(result.is_approved)
        self.assertIsNone(result.practical_score)
        self.assertIsNone(result.final_project_score)
        self.assertIsNone(result.objective_quiz_score)
        self.assertIn('AssessmentResults created: 1', output)

    def test_existing_result_is_untouched(self):
        result = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('31.00'),
        )
        original_updated_at = result.updated_at

        output = self.run_command()
        result.refresh_from_db()

        self.assertEqual(result.practical_score, Decimal('31.00'))
        self.assertEqual(result.updated_at, original_updated_at)
        self.assertIn('Already existing: 1', output)
        self.assertIn('AssessmentResults created: 0', output)

    def test_command_does_not_issue_certificate_or_approve_result(self):
        self.run_command()

        result = AssessmentResult.objects.get(enrollment=self.enrollment)
        self.assertFalse(result.is_approved)
        self.assertEqual(Certificate.objects.count(), 0)

    def test_command_is_safe_to_run_more_than_once(self):
        first_output = self.run_command()
        second_output = self.run_command()

        self.assertEqual(AssessmentResult.objects.filter(enrollment=self.enrollment).count(), 1)
        self.assertIn('AssessmentResults created: 1', first_output)
        self.assertIn('AssessmentResults created: 0', second_output)
        self.assertIn('Already existing: 1', second_output)


@override_settings(SECURE_SSL_REDIRECT=False, MIDDLEWARE=[])
class AssessmentResultPhaseOneTests(APITestCase):
    def setUp(self):
        self.instructor = User.objects.create_user(
            email='phase1-instructor@example.com',
            password='pass',
            first_name='Phase',
            last_name='Instructor',
            role=User.ROLE_INSTRUCTOR,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.other_instructor = User.objects.create_user(
            email='phase1-other@example.com',
            password='pass',
            first_name='Other',
            last_name='Instructor',
            role=User.ROLE_INSTRUCTOR,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.admin = User.objects.create_user(
            email='phase1-admin@example.com',
            password='pass',
            first_name='Admin',
            last_name='User',
            role=User.ROLE_ADMIN,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.student_user = User.objects.create_user(
            email='phase1-student@example.com',
            password='pass',
            first_name='Result',
            last_name='Learner',
            role=User.ROLE_STUDENT,
            approval_status=User.APPROVAL_APPROVED,
        )
        self.student = Student.objects.create(
            user=self.student_user,
            first_name='Result',
            last_name='Learner',
            email='phase1-student-profile@example.com',
            learner_type=Student.LEARNER_ADULT,
            approval_status=Student.STATUS_APPROVED,
        )
        self.course = Course.objects.create(
            title='Assessment Integration',
            description='Phase one course',
            duration_months=2,
            monthly_fee=100,
            fee=200,
            certificate_pass_mark=Decimal('70.00'),
        )
        self.enrollment = Enrollment.objects.create(
            student=self.student,
            course=self.course,
            instructor=self.instructor,
            status=Enrollment.STATUS_COMPLETED,
        )
        Payment.objects.create(
            enrollment=self.enrollment,
            amount=200,
            status=Payment.STATUS_PAID,
        )

    def assessment_results_url(self):
        return reverse('instructor-assessment-results')

    def assessment_result_detail_url(self, result):
        return reverse('instructor-assessment-result-detail', args=[result.id])

    def import_quiz_url(self, result):
        return reverse('instructor-assessment-result-import-quiz-score', args=[result.id])

    def approve_url(self, result):
        return reverse('instructor-assessment-result-approve', args=[result.id])

    def test_one_result_per_enrollment_is_created_on_list_access(self):
        self.client.force_authenticate(self.instructor)

        first = self.client.get(self.assessment_results_url())
        second = self.client.get(self.assessment_results_url())

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(AssessmentResult.objects.filter(enrollment=self.enrollment).count(), 1)

    def test_score_maximum_validation(self):
        result = AssessmentResult.objects.create(enrollment=self.enrollment)

        result.practical_score = Decimal('41.00')
        with self.assertRaises(ValidationError):
            result.full_clean()
        result.practical_score = None

        result.final_project_score = Decimal('41.00')
        with self.assertRaises(ValidationError):
            result.full_clean()
        result.final_project_score = None

        result.objective_quiz_score = Decimal('21.00')
        with self.assertRaises(ValidationError):
            result.full_clean()

    def test_total_percentage_and_incomplete_status(self):
        result = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('30.00'),
            final_project_score=Decimal('20.00'),
        )

        self.assertEqual(result.total_max_score, Decimal('100.00'))
        self.assertEqual(result.overall_score, Decimal('50.00'))
        self.assertEqual(result.percentage, Decimal('50.00'))
        self.assertEqual(result.status, AssessmentResult.STATUS_INCOMPLETE)

    def test_below_pass_and_ready_for_review_statuses(self):
        below = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('20.00'),
            final_project_score=Decimal('20.00'),
            objective_quiz_score=Decimal('10.00'),
        )
        self.assertEqual(below.status, AssessmentResult.STATUS_BELOW_PASS_MARK)

        below.practical_score = Decimal('35.00')
        below.final_project_score = Decimal('30.00')
        below.objective_quiz_score = Decimal('15.00')
        below.save()
        self.assertEqual(below.status, AssessmentResult.STATUS_READY_FOR_REVIEW)

    def test_instructor_and_admin_approval(self):
        result = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.post(self.approve_url(result))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result.refresh_from_db()
        self.assertTrue(result.is_approved)
        self.assertEqual(result.status, AssessmentResult.STATUS_APPROVED)
        self.assertEqual(result.approved_by, self.instructor)
        self.assertIsNotNone(result.approved_at)

        second_student = Student.objects.create(
            first_name='Admin',
            last_name='Approved',
            email='phase1-admin-approved@example.com',
            learner_type=Student.LEARNER_ADULT,
            approval_status=Student.STATUS_APPROVED,
        )
        second_enrollment = Enrollment.objects.create(
            student=second_student,
            course=self.course,
            instructor=self.other_instructor,
            status=Enrollment.STATUS_COMPLETED,
        )
        second_result = AssessmentResult.objects.create(
            enrollment=second_enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('35.00'),
            objective_quiz_score=Decimal('15.00'),
        )
        self.client.force_authenticate(self.admin)

        admin_response = self.client.post(self.approve_url(second_result))

        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        second_result.refresh_from_db()
        self.assertEqual(second_result.approved_by, self.admin)

    def test_instructor_cannot_approve_another_instructors_learner(self):
        result = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
        )
        self.client.force_authenticate(self.other_instructor)

        response = self.client.post(self.approve_url(result))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        result.refresh_from_db()
        self.assertFalse(result.is_approved)

    def test_objective_quiz_score_import_scales_selected_submission(self):
        result = AssessmentResult.objects.create(enrollment=self.enrollment)
        quiz = Assignment.objects.create(
            title='Objective Quiz',
            description='Auto graded quiz.',
            course=self.course,
            instructor=self.instructor,
            due_date='2026-08-01',
            submission_type=Assignment.ASSESSMENT_QUIZ,
            marks=50,
        )
        submission = AssignmentSubmission.objects.create(
            assignment=quiz,
            student=self.student,
            score=25,
            max_score=50,
            status=AssignmentSubmission.STATUS_GRADED,
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.post(
            self.import_quiz_url(result),
            {'submission_id': submission.id},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result.refresh_from_db()
        self.assertEqual(result.objective_quiz_score, Decimal('10.00'))

    def test_online_import_requires_confirmation_before_replacing_manual_score(self):
        result = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            objective_quiz_score=Decimal('17.00'),
        )
        quiz = Assignment.objects.create(
            title='Objective Quiz',
            description='Auto graded quiz.',
            course=self.course,
            instructor=self.instructor,
            due_date='2026-08-01',
            submission_type=Assignment.ASSESSMENT_QUIZ,
            marks=50,
        )
        submission = AssignmentSubmission.objects.create(
            assignment=quiz,
            student=self.student,
            score=25,
            max_score=50,
            status=AssignmentSubmission.STATUS_GRADED,
        )
        self.client.force_authenticate(self.instructor)

        blocked = self.client.post(
            self.import_quiz_url(result),
            {'submission_id': submission.id},
            format='json',
        )
        result.refresh_from_db()

        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(blocked.data['requires_confirmation'])
        self.assertEqual(result.objective_quiz_score, Decimal('17.00'))

        confirmed = self.client.post(
            self.import_quiz_url(result),
            {'submission_id': submission.id, 'replace_existing': True},
            format='json',
        )
        result.refresh_from_db()

        self.assertEqual(confirmed.status_code, status.HTTP_200_OK)
        self.assertEqual(result.objective_quiz_score, Decimal('10.00'))

    def test_instructor_records_practical_score(self):
        result = AssessmentResult.objects.create(enrollment=self.enrollment)
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assessment_result_detail_url(result),
            {'practical_score': '32.50'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result.refresh_from_db()
        self.assertEqual(result.practical_score, Decimal('32.50'))

    def test_instructor_records_final_project_score_and_feedback(self):
        result = AssessmentResult.objects.create(enrollment=self.enrollment)
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assessment_result_detail_url(result),
            {
                'final_project_score': '34.00',
                'final_project_feedback': 'Clear project with good documentation.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result.refresh_from_db()
        self.assertEqual(result.final_project_score, Decimal('34.00'))
        self.assertEqual(result.final_project_feedback, 'Clear project with good documentation.')

    def test_instructor_records_all_component_scores_in_one_patch(self):
        result = AssessmentResult.objects.create(enrollment=self.enrollment)
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assessment_result_detail_url(result),
            {
                'practical_score': '35.00',
                'final_project_score': '30.00',
                'objective_quiz_score': '18.00',
                'final_project_feedback': 'Strong project delivery.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result.refresh_from_db()
        self.assertEqual(result.practical_score, Decimal('35.00'))
        self.assertEqual(result.final_project_score, Decimal('30.00'))
        self.assertEqual(result.objective_quiz_score, Decimal('18.00'))
        self.assertEqual(result.final_project_feedback, 'Strong project delivery.')
        self.assertEqual(result.overall_score, Decimal('83.00'))
        self.assertEqual(result.percentage, Decimal('83.00'))
        self.assertEqual(result.status, AssessmentResult.STATUS_READY_FOR_REVIEW)

    def test_instructor_manually_records_objective_quiz_score(self):
        result = AssessmentResult.objects.create(enrollment=self.enrollment)
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assessment_result_detail_url(result),
            {'objective_quiz_score': '17.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result.refresh_from_db()
        self.assertEqual(result.objective_quiz_score, Decimal('17.00'))
        self.assertEqual(AssignmentSubmission.objects.count(), 0)

    def test_manual_objective_score_rejects_above_maximum(self):
        result = AssessmentResult.objects.create(enrollment=self.enrollment)
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assessment_result_detail_url(result),
            {'objective_quiz_score': '21.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Objective quiz score cannot exceed 20', str(response.data))

    def test_manual_objective_score_rejects_negative_score(self):
        result = AssessmentResult.objects.create(enrollment=self.enrollment)
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assessment_result_detail_url(result),
            {'objective_quiz_score': '-1.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('objective_quiz_score', response.data)

    def test_manual_objective_score_updates_overall_and_ready_status(self):
        result = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('37.00'),
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assessment_result_detail_url(result),
            {'objective_quiz_score': '17.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result.refresh_from_db()
        self.assertEqual(result.overall_score, Decimal('89.00'))
        self.assertEqual(result.percentage, Decimal('89.00'))
        self.assertEqual(result.status, AssessmentResult.STATUS_READY_FOR_REVIEW)

    def test_manual_objective_score_contributes_to_certificate_eligibility(self):
        result = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('37.00'),
            objective_quiz_score=Decimal('17.00'),
        )
        result.approve(self.instructor)

        eligibility = check_combined_result_certificate_eligibility(self.enrollment)

        self.assertTrue(eligibility['eligible'])

    def test_instructor_can_edit_manual_objective_score_before_approval(self):
        result = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            objective_quiz_score=Decimal('15.00'),
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assessment_result_detail_url(result),
            {'objective_quiz_score': '18.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result.refresh_from_db()
        self.assertEqual(result.objective_quiz_score, Decimal('18.00'))

    def test_instructor_cannot_edit_manual_objective_score_after_certificate_issuance(self):
        result = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('37.00'),
            objective_quiz_score=Decimal('17.00'),
            is_approved=True,
            approved_by=self.admin,
            approved_at=timezone.now(),
        )
        Certificate.objects.create(
            student=self.student,
            enrollment=self.enrollment,
            course=self.course,
            completion_date=timezone.localdate(),
            status=Certificate.STATUS_ACTIVE,
            issued_by=self.admin,
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assessment_result_detail_url(result),
            {'objective_quiz_score': '18.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        result.refresh_from_db()
        self.assertEqual(result.objective_quiz_score, Decimal('17.00'))

    def test_historical_reconciled_result_accepts_manual_objective_score(self):
        call_command('reconcile_assessment_results', stdout=StringIO())
        result = AssessmentResult.objects.get(enrollment=self.enrollment)
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assessment_result_detail_url(result),
            {'objective_quiz_score': '16.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result.refresh_from_db()
        self.assertEqual(result.objective_quiz_score, Decimal('16.00'))

    def test_invalid_component_score_is_rejected_by_api(self):
        result = AssessmentResult.objects.create(enrollment=self.enrollment)
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assessment_result_detail_url(result),
            {'practical_score': '41.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('practical_score', response.data)

    def test_instructor_cannot_edit_after_approval(self):
        result = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
            is_approved=True,
            approved_by=self.admin,
            approved_at=timezone.now(),
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assessment_result_detail_url(result),
            {'practical_score': '36.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Approved assessment results cannot be changed by instructors.', str(response.data))

    def test_instructor_cannot_edit_manual_objective_score_after_approval(self):
        result = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('37.00'),
            objective_quiz_score=Decimal('17.00'),
            is_approved=True,
            approved_by=self.admin,
            approved_at=timezone.now(),
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.patch(
            self.assessment_result_detail_url(result),
            {'objective_quiz_score': '18.00'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Approved assessment results cannot be changed by instructors.', str(response.data))

    def test_no_certificate_is_automatically_issued(self):
        from certificates.models import Certificate

        result = AssessmentResult.objects.create(
            enrollment=self.enrollment,
            practical_score=Decimal('35.00'),
            final_project_score=Decimal('30.00'),
            objective_quiz_score=Decimal('15.00'),
        )
        self.client.force_authenticate(self.instructor)

        response = self.client.post(self.approve_url(result))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Certificate.objects.filter(enrollment=self.enrollment).exists())
