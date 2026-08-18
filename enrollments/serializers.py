from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from courses.serializers import CourseSerializer
from students.serializers import StudentSerializer
from users.serializers import UserSerializer

from .models import Assignment, AssignmentQuestion, AssignmentSubmission, AssessmentResult, Attendance, Enrollment, LearningResource, LessonNote, ProgressReport


class EnrollmentSerializer(serializers.ModelSerializer):
    student_detail = StudentSerializer(source='student', read_only=True)
    course_detail = CourseSerializer(source='course', read_only=True)
    instructor_detail = UserSerializer(source='instructor', read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            'id',
            'student',
            'student_detail',
            'course',
            'course_detail',
            'instructor',
            'instructor_detail',
            'status',
            'enrolled_at',
            'start_date',
            'end_date',
            'notes',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['enrolled_at', 'created_at', 'updated_at']

    def validate_instructor(self, value):
        if value and value.role != 'instructor':
            raise serializers.ValidationError('Assigned user must have the instructor role.')
        return value

    def validate_student(self, value):
        if value.approval_status != value.STATUS_APPROVED:
            raise serializers.ValidationError('Only approved learners can be enrolled.')
        return value


class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='enrollment.course.title', read_only=True)

    class Meta:
        model = Attendance
        fields = [
            'id',
            'enrollment',
            'student_name',
            'course_title',
            'date',
            'status',
            'remarks',
            'recorded_by',
            'created_at',
        ]
        read_only_fields = ['recorded_by', 'created_at']

    def get_student_name(self, obj):
        return str(obj.enrollment.student)

    def validate_enrollment(self, value):
        request = self.context['request']
        if request.user.role == 'instructor' and value.instructor_id != request.user.id:
            raise serializers.ValidationError('You can only record attendance for your assigned enrollments.')
        return value


class LessonNoteSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)

    class Meta:
        model = LessonNote
        fields = [
            'id',
            'course',
            'course_title',
            'title',
            'content',
            'lesson_date',
            'created_at',
        ]
        read_only_fields = ['created_at']

    def validate_course(self, value):
        request = self.context['request']
        if request.user.role == 'instructor' and not value.enrollments.filter(
            instructor=request.user
        ).exists():
            raise serializers.ValidationError('You can only add lesson notes for your assigned courses.')
        return value


class ProgressReportSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='enrollment.course.title', read_only=True)

    class Meta:
        model = ProgressReport
        fields = [
            'id',
            'enrollment',
            'student_name',
            'course_title',
            'progress_score',
            'strengths',
            'areas_for_improvement',
            'instructor_comment',
            'created_by',
            'created_at',
        ]
        read_only_fields = ['created_by', 'created_at']

    def get_student_name(self, obj):
        return str(obj.enrollment.student)

    def validate_progress_score(self, value):
        if value > 100:
            raise serializers.ValidationError('Progress score must be between 0 and 100.')
        return value

    def validate_enrollment(self, value):
        request = self.context['request']
        if request.user.role == 'instructor' and value.instructor_id != request.user.id:
            raise serializers.ValidationError('You can only create reports for your assigned enrollments.')
        return value


class LearningResourceSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    instructor_name = serializers.SerializerMethodField()
    target_student_name = serializers.SerializerMethodField()
    target_label = serializers.SerializerMethodField()

    class Meta:
        model = LearningResource
        fields = [
            'id',
            'title',
            'description',
            'resource_type',
            'url',
            'course',
            'course_title',
            'instructor',
            'instructor_name',
            'target_student',
            'target_student_name',
            'target_label',
            'is_published',
            'published_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['published_at', 'created_at', 'updated_at']
        extra_kwargs = {'instructor': {'required': False}}

    def get_instructor_name(self, obj):
        return f'{obj.instructor.first_name} {obj.instructor.last_name}'.strip() or obj.instructor.email

    def get_target_student_name(self, obj):
        return str(obj.target_student) if obj.target_student else ''

    def get_target_label(self, obj):
        return str(obj.target_student) if obj.target_student else 'Entire course'

    def validate_instructor(self, value):
        request = self.context['request']
        if request.user.role == 'instructor':
            return request.user
        if value.role != 'instructor':
            raise serializers.ValidationError('Assigned user must have the instructor role.')
        return value

    def validate_url(self, value):
        if value and not value.lower().startswith(('http://', 'https://')):
            raise serializers.ValidationError('Enter a valid http:// or https:// URL.')
        return value

    def validate_course(self, value):
        request = self.context['request']
        if request.user.role == 'instructor' and not value.enrollments.filter(
            instructor=request.user
        ).exists():
            raise serializers.ValidationError('You can only create resources for your assigned courses.')
        return value

    def validate(self, attrs):
        request = self.context['request']
        if request.user.role == 'instructor':
            attrs['instructor'] = request.user
        elif not attrs.get('instructor') and not getattr(self.instance, 'instructor_id', None):
            raise serializers.ValidationError({'instructor': 'Select an instructor for this resource.'})

        resource_type = attrs.get('resource_type') or getattr(self.instance, 'resource_type', LearningResource.RESOURCE_DOCUMENT)
        description = (attrs.get('description', getattr(self.instance, 'description', '')) or '').strip()
        url = (attrs.get('url', getattr(self.instance, 'url', '')) or '').strip()
        course = attrs.get('course') or getattr(self.instance, 'course', None)
        target_student = attrs.get('target_student')
        if 'target_student' not in attrs and self.instance:
            target_student = self.instance.target_student

        if resource_type == LearningResource.RESOURCE_NOTE:
            if not description:
                raise serializers.ValidationError({'description': 'Description is required for note resources.'})
        elif not url:
            raise serializers.ValidationError({'url': 'URL is required for this resource type.'})

        if target_student and course:
            if not target_student.enrollments.filter(course=course).exists():
                raise serializers.ValidationError({
                    'target_student': 'Selected learner must be enrolled in the selected course.'
                })
            if request.user.role == 'instructor' and not target_student.enrollments.filter(
                course=course,
                instructor=request.user,
            ).exists():
                raise PermissionDenied('You can only target learners assigned to you for this course.')

        return attrs


class AssignmentQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssignmentQuestion
        fields = [
            'id',
            'question_text',
            'option_a',
            'option_b',
            'option_c',
            'option_d',
            'correct_answer',
            'marks',
        ]


class StudentAssignmentQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssignmentQuestion
        fields = [
            'id',
            'question_text',
            'option_a',
            'option_b',
            'option_c',
            'option_d',
            'marks',
        ]


class AssignmentSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    target_student_name = serializers.SerializerMethodField()
    instructor_name = serializers.SerializerMethodField()
    questions = AssignmentQuestionSerializer(many=True, required=False)
    question_count = serializers.IntegerField(source='questions.count', read_only=True)

    class Meta:
        model = Assignment
        fields = [
            'id',
            'title',
            'description',
            'course',
            'course_title',
            'target_student',
            'target_student_name',
            'instructor',
            'instructor_name',
            'due_date',
            'submission_type',
            'marks',
            'questions',
            'question_count',
            'created_at',
            'is_active',
        ]
        read_only_fields = ['created_at']
        extra_kwargs = {'instructor': {'required': False}}

    def get_instructor_name(self, obj):
        return f'{obj.instructor.first_name} {obj.instructor.last_name}'.strip()

    def get_target_student_name(self, obj):
        return str(obj.target_student) if obj.target_student else 'Group'

    def validate_instructor(self, value):
        request = self.context['request']
        if request.user.role == 'instructor':
            return request.user
        if value.role != 'instructor':
            raise serializers.ValidationError('Assigned user must have the instructor role.')
        return value

    def validate_course(self, value):
        request = self.context['request']
        if request.user.role == 'instructor' and not value.enrollments.filter(
            instructor=request.user
        ).exists():
            raise serializers.ValidationError('You can only create assignments for your assigned courses.')
        return value

    def validate(self, attrs):
        request = self.context['request']
        if request.user.role == 'instructor':
            attrs['instructor'] = request.user
        elif not attrs.get('instructor') and not getattr(self.instance, 'instructor_id', None):
            raise serializers.ValidationError({'instructor': 'Select an instructor for this assignment.'})
        course = attrs.get('course') or getattr(self.instance, 'course', None)
        target_student = attrs.get('target_student')
        if target_student and course:
            if not target_student.enrollments.filter(course=course).exists():
                raise serializers.ValidationError({
                    'target_student': 'Selected student must be enrolled in the selected course.'
                })
            if request.user.role == 'instructor' and not target_student.enrollments.filter(
                course=course,
                instructor=request.user,
            ).exists():
                raise PermissionDenied(
                    'You can only assign assessments to students assigned to you.'
                )
        submission_type = attrs.get('submission_type') or getattr(self.instance, 'submission_type', Assignment.ASSESSMENT_QUIZ)
        questions = self.initial_data.get('questions')
        if submission_type == Assignment.ASSESSMENT_QUIZ and self.instance is None and not questions:
            raise serializers.ValidationError({'questions': 'Add at least one multiple-choice question for a quiz.'})
        return attrs

    def create(self, validated_data):
        questions = validated_data.pop('questions', [])
        assignment = super().create(validated_data)
        self._save_questions(assignment, questions)
        return assignment

    def update(self, instance, validated_data):
        questions = validated_data.pop('questions', None)
        assignment = super().update(instance, validated_data)
        if questions is not None:
            assignment.questions.all().delete()
            self._save_questions(assignment, questions)
        return assignment

    def _save_questions(self, assignment, questions):
        if assignment.submission_type != Assignment.ASSESSMENT_QUIZ:
            return
        AssignmentQuestion.objects.bulk_create([
            AssignmentQuestion(assignment=assignment, **question)
            for question in questions
        ])


class AssignmentSharingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Assignment
        fields = [
            'is_public',
            'share_expires_at',
            'max_guest_attempts',
        ]

    def validate_max_guest_attempts(self, value):
        if value is not None and value < 1:
            raise serializers.ValidationError('Maximum guest attempts must be at least 1.')
        return value


class AssessmentResultSerializer(serializers.ModelSerializer):
    enrollment_id = serializers.IntegerField(source='enrollment.id', read_only=True)
    student_id = serializers.IntegerField(source='enrollment.student.id', read_only=True)
    student_name = serializers.SerializerMethodField()
    course_id = serializers.IntegerField(source='enrollment.course.id', read_only=True)
    course_title = serializers.CharField(source='enrollment.course.title', read_only=True)
    pass_mark = serializers.DecimalField(
        source='enrollment.course.certificate_pass_mark',
        max_digits=5,
        decimal_places=2,
        read_only=True,
    )
    instructor_id = serializers.IntegerField(source='enrollment.instructor.id', read_only=True)
    approved_by_name = serializers.SerializerMethodField()
    is_complete = serializers.BooleanField(read_only=True)
    meets_pass_mark = serializers.BooleanField(read_only=True)
    certificate_id = serializers.SerializerMethodField()
    certificate_number = serializers.SerializerMethodField()
    certificate_status = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentResult
        fields = [
            'id',
            'enrollment_id',
            'student_id',
            'student_name',
            'course_id',
            'course_title',
            'pass_mark',
            'instructor_id',
            'practical_max_score',
            'practical_score',
            'final_project_max_score',
            'final_project_score',
            'objective_quiz_max_score',
            'objective_quiz_score',
            'final_project_feedback',
            'overall_score',
            'total_max_score',
            'percentage',
            'status',
            'is_complete',
            'meets_pass_mark',
            'certificate_id',
            'certificate_number',
            'certificate_status',
            'is_approved',
            'approved_by',
            'approved_by_name',
            'approved_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'overall_score',
            'total_max_score',
            'percentage',
            'status',
            'is_approved',
            'approved_by',
            'approved_at',
            'created_at',
            'updated_at',
        ]

    def get_student_name(self, obj):
        return str(obj.enrollment.student)

    def get_approved_by_name(self, obj):
        if not obj.approved_by:
            return ''
        return f'{obj.approved_by.first_name} {obj.approved_by.last_name}'.strip() or obj.approved_by.email

    def get_certificate(self, obj):
        return getattr(obj.enrollment, 'certificate', None)

    def get_certificate_id(self, obj):
        certificate = self.get_certificate(obj)
        return certificate.id if certificate else None

    def get_certificate_number(self, obj):
        certificate = self.get_certificate(obj)
        return certificate.certificate_number if certificate else ''

    def get_certificate_status(self, obj):
        certificate = self.get_certificate(obj)
        if not certificate:
            return ''
        return 'issued' if certificate.is_active() else certificate.status


class AssessmentResultUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssessmentResult
        fields = [
            'practical_score',
            'final_project_score',
            'objective_quiz_score',
            'final_project_feedback',
        ]

    def validate(self, attrs):
        instance = self.instance
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        certificate = getattr(instance.enrollment, 'certificate', None)
        if certificate and certificate.is_active():
            raise serializers.ValidationError('Certified assessment results cannot be changed. Use certificate revoke/reissue for material corrections.')
        if instance.is_approved and getattr(user, 'role', None) != 'admin':
            raise serializers.ValidationError('Approved assessment results cannot be changed by instructors.')
        practical_score = attrs.get('practical_score', instance.practical_score)
        final_project_score = attrs.get('final_project_score', instance.final_project_score)
        objective_quiz_score = attrs.get('objective_quiz_score', instance.objective_quiz_score)
        if practical_score is not None and practical_score > instance.practical_max_score:
            raise serializers.ValidationError({
                'practical_score': 'Practical score cannot exceed its maximum score.'
            })
        if final_project_score is not None and final_project_score > instance.final_project_max_score:
            raise serializers.ValidationError({
                'final_project_score': 'Final project score cannot exceed its maximum score.'
            })
        if objective_quiz_score is not None and objective_quiz_score > instance.objective_quiz_max_score:
            raise serializers.ValidationError({
                'objective_quiz_score': f'Objective quiz score cannot exceed {instance.objective_quiz_max_score:g}.'
            })
        return attrs


class AssessmentResultImportQuizSerializer(serializers.Serializer):
    submission_id = serializers.IntegerField()

    def validate_submission_id(self, value):
        try:
            return AssignmentSubmission.objects.select_related('assignment').get(pk=value)
        except AssignmentSubmission.DoesNotExist:
            raise serializers.ValidationError('Quiz submission not found.')


class PublicAssessmentSerializer(serializers.ModelSerializer):
    course = serializers.CharField(source='course.title', read_only=True)
    duration = serializers.IntegerField(source='course.duration_months', read_only=True)
    instructions = serializers.CharField(source='description', read_only=True)
    question_count = serializers.IntegerField(source='questions.count', read_only=True)
    start_date = serializers.SerializerMethodField()
    end_date = serializers.DateField(source='due_date', read_only=True)
    academy_name = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = [
            'title',
            'course',
            'duration',
            'instructions',
            'question_count',
            'start_date',
            'end_date',
            'academy_name',
        ]

    def get_start_date(self, obj):
        return obj.created_at.date() if obj.created_at else None

    def get_academy_name(self, obj):
        return 'Velttech Academy'


class AssignmentSubmissionSerializer(serializers.ModelSerializer):
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)
    assignment_description = serializers.CharField(source='assignment.description', read_only=True)
    assignment_due_date = serializers.DateField(source='assignment.due_date', read_only=True)
    assignment_submission_type = serializers.CharField(source='assignment.submission_type', read_only=True)
    assignment_marks = serializers.IntegerField(source='assignment.marks', read_only=True)
    assignment_course = serializers.IntegerField(source='assignment.course.id', read_only=True)
    course_title = serializers.CharField(source='assignment.course.title', read_only=True)
    student_name = serializers.SerializerMethodField()
    grade = serializers.IntegerField(source='score', read_only=True)
    graded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = AssignmentSubmission
        fields = [
            'id',
            'assignment',
            'assignment_title',
            'assignment_description',
            'assignment_due_date',
            'assignment_submission_type',
            'assignment_marks',
            'assignment_course',
            'course_title',
            'student',
            'student_name',
            'quiz_answers',
            'submitted_at',
            'score',
            'grade',
            'percentage',
            'letter_grade',
            'max_score',
            'feedback',
            'graded_by',
            'graded_by_name',
            'graded_at',
            'status',
        ]
        read_only_fields = [
            'assignment',
            'student',
            'submitted_at',
            'status',
            'graded_by',
            'graded_by_name',
            'graded_at',
        ]

    def get_student_name(self, obj):
        return str(obj.student)

    def get_graded_by_name(self, obj):
        if not obj.graded_by:
            return ''
        return f'{obj.graded_by.first_name} {obj.graded_by.last_name}'.strip() or obj.graded_by.email

    def validate_score(self, value):
        if value is not None and value > 100:
            raise serializers.ValidationError('Score must be between 0 and 100.')
        return value

class GradeAssignmentSubmissionSerializer(serializers.ModelSerializer):
    grade = serializers.IntegerField(source='score', required=False)

    class Meta:
        model = AssignmentSubmission
        fields = ['score', 'grade', 'max_score', 'feedback', 'status']

    def validate_score(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('Grade cannot be below 0.')
        max_score = self.initial_data.get('max_score') or getattr(self.instance, 'max_score', None)
        if max_score is None and self.instance:
            max_score = self.instance.assignment.marks or 100
        if value is not None and max_score is not None and value > int(max_score):
            raise serializers.ValidationError(f'Grade cannot exceed max score ({max_score}).')
        return value

    def validate_max_score(self, value):
        if value <= 0:
            raise serializers.ValidationError('Max score must be greater than 0.')
        return value

    def validate_status(self, value):
        allowed = {
            AssignmentSubmission.STATUS_GRADED,
            AssignmentSubmission.STATUS_RETURNED,
        }
        if value not in allowed:
            raise serializers.ValidationError('Status must be graded or returned.')
        return value

    def validate(self, attrs):
        status = attrs.get('status') or AssignmentSubmission.STATUS_GRADED
        score = attrs.get('score', getattr(self.instance, 'score', None))
        feedback = (attrs.get('feedback') or getattr(self.instance, 'feedback', '') or '').strip()
        max_score = attrs.get('max_score') or getattr(self.instance, 'max_score', None) or self.instance.assignment.marks or 100
        if status == AssignmentSubmission.STATUS_GRADED and score is None:
            raise serializers.ValidationError({'grade': 'Grade is required when grading a submission.'})
        if status == AssignmentSubmission.STATUS_GRADED and not feedback:
            raise serializers.ValidationError({'feedback': 'Feedback should not be empty when grading.'})
        if score is not None and score > max_score:
            raise serializers.ValidationError({'grade': f'Grade cannot exceed max score ({max_score}).'})
        attrs['status'] = status
        attrs['max_score'] = max_score
        attrs['feedback'] = feedback
        return attrs


class MyAssignmentSerializer(AssignmentSerializer):
    submission = serializers.SerializerMethodField()
    submissions = serializers.SerializerMethodField()
    questions = serializers.SerializerMethodField()

    class Meta(AssignmentSerializer.Meta):
        fields = AssignmentSerializer.Meta.fields + [
            'submission',
            'submissions',
        ]

    def get_submission(self, obj):
        request = self.context['request']
        if request.user.role != 'student':
            return None
        submission = next(iter(obj.visible_submissions), None)
        return AssignmentSubmissionSerializer(submission, context=self.context).data if submission else None

    def get_submissions(self, obj):
        request = self.context['request']
        if request.user.role == 'student':
            return []
        return AssignmentSubmissionSerializer(obj.visible_submissions, many=True, context=self.context).data

    def get_questions(self, obj):
        if obj.submission_type != Assignment.ASSESSMENT_QUIZ:
            return []
        return StudentAssignmentQuestionSerializer(obj.questions.all(), many=True).data
