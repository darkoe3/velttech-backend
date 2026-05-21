from rest_framework import serializers

from courses.serializers import CourseSerializer
from students.serializers import StudentSerializer
from users.serializers import UserSerializer

from .models import (
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
    instructor_name = serializers.SerializerMethodField()

    class Meta:
        model = Assignment
        fields = [
            'id',
            'title',
            'description',
            'course',
            'course_title',
            'instructor',
            'instructor_name',
            'due_date',
            'created_at',
            'is_active',
        ]
        read_only_fields = ['instructor', 'created_at']

    def get_instructor_name(self, obj):
        return f'{obj.instructor.first_name} {obj.instructor.last_name}'.strip()

    def validate_course(self, value):
        request = self.context['request']
        if request.user.role == 'instructor' and not value.enrollments.filter(
            instructor=request.user
        ).exists():
            raise serializers.ValidationError('You can only create assignments for your assigned courses.')
        return value


class AssignmentSubmissionSerializer(serializers.ModelSerializer):
    assignment_title = serializers.CharField(source='assignment.title', read_only=True)
    course_title = serializers.CharField(source='assignment.course.title', read_only=True)
    student_name = serializers.SerializerMethodField()

    class Meta:
        model = AssignmentSubmission
        fields = [
            'id',
            'assignment',
            'assignment_title',
            'course_title',
            'student',
            'student_name',
            'submission_text',
            'submitted_at',
            'score',
            'feedback',
            'status',
        ]
        read_only_fields = ['assignment', 'student', 'submitted_at', 'status']

    def get_student_name(self, obj):
        return str(obj.student)

    def validate_score(self, value):
        if value is not None and value > 100:
            raise serializers.ValidationError('Score must be between 0 and 100.')
        return value


class GradeAssignmentSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AssignmentSubmission
        fields = ['score', 'feedback']

    def validate_score(self, value):
        if value is not None and value > 100:
            raise serializers.ValidationError('Score must be between 0 and 100.')
        return value


class MyAssignmentSerializer(AssignmentSerializer):
    submission = serializers.SerializerMethodField()
    submissions = serializers.SerializerMethodField()

    class Meta(AssignmentSerializer.Meta):
        fields = AssignmentSerializer.Meta.fields + ['submission', 'submissions']

    def get_submission(self, obj):
        request = self.context['request']
        if request.user.role != 'student':
            return None
        submission = next(iter(obj.visible_submissions), None)
        return AssignmentSubmissionSerializer(submission).data if submission else None

    def get_submissions(self, obj):
        request = self.context['request']
        if request.user.role == 'student':
            return []
        return AssignmentSubmissionSerializer(obj.visible_submissions, many=True).data
