from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from students.models import Parent, Student
from courses.models import Course
from enrollments.models import Attendance, Enrollment, ProgressReport
from payments.models import Payment
from notifications.models import Notification
from .models import ActivityLog

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'role']


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        validate_password(attrs['new_password'])
        return attrs


class ActivityLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = ActivityLog
        fields = ['id', 'user', 'user_email', 'role', 'action', 'description', 'ip_address', 'created_at']


class DashboardCourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ['id', 'title', 'description', 'duration_months', 'monthly_fee', 'is_active']


class DashboardChildSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    courses = serializers.SerializerMethodField()
    attendance_summary = serializers.SerializerMethodField()
    latest_progress_report = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            'id',
            'full_name',
            'first_name',
            'other_name',
            'last_name',
            'approval_status',
            'courses',
            'attendance_summary',
            'latest_progress_report',
        ]

    def get_full_name(self, obj):
        return str(obj)

    def get_courses(self, obj):
        courses = [enrollment.course for enrollment in obj.enrollments.all()]
        return DashboardCourseSerializer(courses, many=True).data

    def get_attendance_summary(self, obj):
        records = Attendance.objects.filter(enrollment__student=obj)
        return {
            'total': records.count(),
            'present': records.filter(status=Attendance.STATUS_PRESENT).count(),
            'absent': records.filter(status=Attendance.STATUS_ABSENT).count(),
            'late': records.filter(status=Attendance.STATUS_LATE).count(),
            'excused': records.filter(status=Attendance.STATUS_EXCUSED).count(),
        }

    def get_latest_progress_report(self, obj):
        report = ProgressReport.objects.filter(
            enrollment__student=obj,
        ).select_related('enrollment__course').first()
        return DashboardProgressReportSerializer(report).data if report else None


class DashboardPaymentSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='enrollment.course.title', read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id',
            'amount',
            'payment_method',
            'status',
            'transaction_reference',
            'paid_at',
            'created_at',
            'student_name',
            'course_title',
        ]

    def get_student_name(self, obj):
        return str(obj.enrollment.student)


class DashboardNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'audience', 'created_at']


class DashboardAttendanceSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='enrollment.course.title', read_only=True)

    class Meta:
        model = Attendance
        fields = ['id', 'date', 'status', 'remarks', 'course_title']


class DashboardProgressReportSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='enrollment.course.title', read_only=True)

    class Meta:
        model = ProgressReport
        fields = [
            'id',
            'course_title',
            'progress_score',
            'strengths',
            'areas_for_improvement',
            'instructor_comment',
            'created_at',
        ]


class InstructorCourseSerializer(serializers.ModelSerializer):
    assigned_students_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Course
        fields = [
            'id',
            'title',
            'description',
            'duration_months',
            'is_active',
            'assigned_students_count',
        ]


class InstructorStudentSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    parent_name = serializers.SerializerMethodField()
    parent_phone = serializers.SerializerMethodField()
    assigned_course = serializers.SerializerMethodField()
    enrollment_status = serializers.SerializerMethodField()

    class Meta:
        model = Student
        fields = [
            'id',
            'full_name',
            'school_name',
            'parent_name',
            'parent_phone',
            'assigned_course',
            'enrollment_status',
        ]

    def get_full_name(self, obj):
        return str(obj)

    def get_parent_name(self, obj):
        return str(obj.parent) if obj.parent else None

    def get_parent_phone(self, obj):
        return obj.parent.phone_number if obj.parent else None

    def get_assigned_course(self, obj):
        enrollment = getattr(obj, 'instructor_enrollment', None)
        return enrollment.course.title if enrollment else None

    def get_enrollment_status(self, obj):
        enrollment = getattr(obj, 'instructor_enrollment', None)
        return enrollment.status if enrollment else None


class InstructorEnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='course.title', read_only=True)
    parent_name = serializers.SerializerMethodField()
    parent_phone = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = [
            'id',
            'student_name',
            'course_title',
            'start_date',
            'status',
            'parent_name',
            'parent_phone',
        ]

    def get_student_name(self, obj):
        return str(obj.student)

    def get_parent_name(self, obj):
        return str(obj.student.parent) if obj.student.parent else None

    def get_parent_phone(self, obj):
        return obj.student.parent.phone_number if obj.student.parent else None


class RecentRegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'role', 'date_joined']


class RegisterSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    phone_number = serializers.CharField(max_length=20, write_only=True)
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(
        choices=[User.ROLE_PARENT, User.ROLE_STUDENT],
        default=User.ROLE_PARENT,
    )

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        validate_password(attrs['password'])
        return attrs

    def create(self, validated_data):
        validated_data.pop('confirm_password')
        phone_number = validated_data.pop('phone_number')
        user = User.objects.create_user(**validated_data)

        if user.role == User.ROLE_PARENT:
            Parent.objects.create(
                user=user,
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                phone_number=phone_number,
            )
        else:
            Student.objects.create(
                user=user,
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                phone_number=phone_number,
            )
        return user


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Old password is incorrect.')
        return value

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_password']:
            raise serializers.ValidationError({'confirm_password': 'Passwords do not match.'})
        validate_password(attrs['new_password'], self.context['request'].user)
        return attrs


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = 'email'

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        token['role'] = user.role
        token['first_name'] = user.first_name
        token['last_name'] = user.last_name
        return token
