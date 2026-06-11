from pathlib import Path

from rest_framework import serializers

from courses.serializers import CourseSerializer
from students.serializers import StudentSerializer
from users.serializers import UserSerializer

from .models import (
    ASSIGNMENT_FILE_EXTENSIONS,
    ASSIGNMENT_FILE_MAX_SIZE,
    Assignment,
    AssignmentSubmission,
    Attendance,
    Enrollment,
    LessonNote,
    ProgressReport,
)


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
        extra_kwargs = {'instructor': {'required': False}}

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


class AssignmentSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    target_student_name = serializers.SerializerMethodField()
    instructor_name = serializers.SerializerMethodField()

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
            'created_at',
            'is_active',
        ]
        read_only_fields = ['created_at']

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
        if target_student and course and not target_student.enrollments.filter(course=course).exists():
            raise serializers.ValidationError({
                'target_student': 'Selected student must be enrolled in the selected course.'
            })
        return attrs


class AssignmentSubmissionSerializer(serializers.ModelSerializer):
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)
    assignment_description = serializers.CharField(source='assignment.description', read_only=True)
    assignment_due_date = serializers.DateField(source='assignment.due_date', read_only=True)
    assignment_submission_type = serializers.CharField(source='assignment.submission_type', read_only=True)
    assignment_marks = serializers.IntegerField(source='assignment.marks', read_only=True)
    course_title = serializers.CharField(source='assignment.course.title', read_only=True)
    student_name = serializers.SerializerMethodField()
    uploaded_file_url = serializers.SerializerMethodField()
    grade = serializers.IntegerField(source='score', read_only=True)
    graded_by_name = serializers.SerializerMethodField()
    text_answer_preview = serializers.SerializerMethodField()

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
            'submission_text',
            'text_answer',
            'uploaded_file',
            'uploaded_file_name',
            'uploaded_file_url',
            'submitted_at',
            'score',
            'grade',
            'max_score',
            'feedback',
            'graded_by',
            'graded_by_name',
            'graded_at',
            'status',
            'text_answer_preview',
        ]
        read_only_fields = [
            'assignment',
            'student',
            'submitted_at',
            'status',
            'uploaded_file_name',
            'uploaded_file_url',
            'graded_by',
            'graded_by_name',
            'graded_at',
            'text_answer_preview',
        ]
        extra_kwargs = {'uploaded_file': {'write_only': True}}

    def get_student_name(self, obj):
        return str(obj.student)

    def get_graded_by_name(self, obj):
        if not obj.graded_by:
            return ''
        return f'{obj.graded_by.first_name} {obj.graded_by.last_name}'.strip() or obj.graded_by.email

    def get_text_answer_preview(self, obj):
        answer = obj.text_answer or obj.submission_text or ''
        return answer[:180]

    def get_uploaded_file_url(self, obj):
        request = self.context.get('request')
        if not obj.uploaded_file:
            return ''
        if request and request.user.role == 'instructor':
            return request.build_absolute_uri(f'/api/instructor/submissions/{obj.pk}/file/')
        if request and request.user.role == 'student' and obj.student.user_id == request.user.id:
            return request.build_absolute_uri(f'/api/my-assignments/submissions/{obj.pk}/file/')
        if request and request.user.role == 'parent' and obj.student.parent and obj.student.parent.user_id == request.user.id:
            return request.build_absolute_uri(f'/api/my-assignments/submissions/{obj.pk}/file/')
        return ''

    def validate_score(self, value):
        if value is not None and value > 100:
            raise serializers.ValidationError('Score must be between 0 and 100.')
        return value

    def validate_uploaded_file(self, value):
        extension = Path(value.name).suffix.lower()
        if extension not in ASSIGNMENT_FILE_EXTENSIONS:
            allowed = ', '.join(sorted(ASSIGNMENT_FILE_EXTENSIONS))
            raise serializers.ValidationError(f'Unsupported file type. Allowed files: {allowed}.')
        if value.size > ASSIGNMENT_FILE_MAX_SIZE:
            raise serializers.ValidationError('Assignment files must be 10MB or smaller.')
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
    allowed_file_extensions = serializers.SerializerMethodField()
    max_file_size_mb = serializers.SerializerMethodField()

    class Meta(AssignmentSerializer.Meta):
        fields = AssignmentSerializer.Meta.fields + [
            'submission',
            'submissions',
            'allowed_file_extensions',
            'max_file_size_mb',
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

    def get_allowed_file_extensions(self, obj):
        return sorted(ASSIGNMENT_FILE_EXTENSIONS)

    def get_max_file_size_mb(self, obj):
        return ASSIGNMENT_FILE_MAX_SIZE // (1024 * 1024)
