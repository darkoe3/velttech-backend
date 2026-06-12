from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from courses.serializers import CourseSerializer
from students.serializers import StudentSerializer
from users.serializers import UserSerializer

from .models import Assignment, AssignmentQuestion, AssignmentSubmission, Attendance, Enrollment, LessonNote, ProgressReport


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


class AssignmentSubmissionSerializer(serializers.ModelSerializer):
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)
    assignment_description = serializers.CharField(source='assignment.description', read_only=True)
    assignment_due_date = serializers.DateField(source='assignment.due_date', read_only=True)
    assignment_submission_type = serializers.CharField(source='assignment.submission_type', read_only=True)
    assignment_marks = serializers.IntegerField(source='assignment.marks', read_only=True)
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
