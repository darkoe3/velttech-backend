from decimal import Decimal

from django.db.models import Q
from rest_framework import serializers
from django.utils import timezone

from .models import Certificate
from enrollments.models import Enrollment


CERTIFICATE_PROGRAMME_NAME = 'Young Innovators Academy'


def grade_for_score(score):
    if score is None:
        return ''
    score = Decimal(score)
    if score >= 80:
        return 'A'
    if score >= 70:
        return 'B'
    if score >= 60:
        return 'C'
    if score >= 50:
        return 'D'
    return 'F'


def default_certificate_type(score):
    if score is not None and Decimal(score) >= 90:
        return Certificate.TYPE_EXCELLENCE
    return Certificate.TYPE_COMPLETION


def calculate_final_score(enrollment):
    from enrollments.models import AssignmentSubmission

    submissions = AssignmentSubmission.objects.select_related('assignment').filter(
        student=enrollment.student,
        assignment__course=enrollment.course,
        score__isnull=False,
        status=AssignmentSubmission.STATUS_GRADED,
    )
    percentages = [
        Decimal(str(submission.percentage))
        for submission in submissions
        if submission.percentage is not None
    ]
    if not percentages:
        return None
    return round(sum(percentages) / len(percentages), 2)


def calculate_attendance_percentage(enrollment):
    from enrollments.models import Attendance

    records = Attendance.objects.filter(enrollment=enrollment)
    total = records.count()
    if total == 0:
        return None
    attended = records.filter(
        Q(status=Attendance.STATUS_PRESENT) | Q(status=Attendance.STATUS_LATE)
    ).count()
    return round((Decimal(attended) / Decimal(total)) * Decimal('100'), 2)


class CertificateSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    programme_name = serializers.SerializerMethodField()
    specialization_title = serializers.CharField(source='course.title', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    issued_by_name = serializers.SerializerMethodField()
    enrollment_id = serializers.IntegerField(source='enrollment.id', read_only=True)

    class Meta:
        model = Certificate
        fields = [
            'id',
            'certificate_number',
            'student',
            'student_name',
            'enrollment_id',
            'course',
            'programme_name',
            'specialization_title',
            'course_title',
            'issued_by',
            'issued_by_name',
            'issued_at',
            'issue_date',
            'completion_date',
            'certificate_type',
            'final_score',
            'final_grade',
            'attendance_percentage',
            'skills_covered',
            'status',
            'verification_code',
            'qr_code',
            'pdf_file',
            'certificate_file',
            'revoked_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'certificate_number',
            'issued_at',
            'issue_date',
            'verification_code',
            'qr_code',
            'pdf_file',
            'certificate_file',
            'created_at',
            'updated_at',
        ]

    def get_student_name(self, obj):
        names = [obj.student.first_name, obj.student.other_name, obj.student.last_name]
        return ' '.join(name for name in names if name)

    def get_programme_name(self, obj):
        return CERTIFICATE_PROGRAMME_NAME

    def get_issued_by_name(self, obj):
        if obj.issued_by:
            return f"{obj.issued_by.first_name} {obj.issued_by.last_name}"
        return "Velttech Academy"


class CertificateListSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    programme_name = serializers.SerializerMethodField()
    specialization_title = serializers.CharField(source='course.title', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)

    class Meta:
        model = Certificate
        fields = [
            'id',
            'certificate_number',
            'student',
            'student_name',
            'course',
            'programme_name',
            'specialization_title',
            'course_title',
            'status',
            'certificate_type',
            'skills_covered',
            'completion_date',
            'issue_date',
            'issued_at',
            'verification_code',
        ]

    def get_student_name(self, obj):
        names = [obj.student.first_name, obj.student.other_name, obj.student.last_name]
        return ' '.join(name for name in names if name)

    def get_programme_name(self, obj):
        return CERTIFICATE_PROGRAMME_NAME


class CertificateIssuanceSerializer(serializers.Serializer):
    """Serializer for issuing certificates"""
    enrollment_id = serializers.IntegerField()
    completion_date = serializers.DateField()
    certificate_type = serializers.ChoiceField(
        choices=Certificate.CERTIFICATE_TYPE_CHOICES,
        required=False,
    )
    final_score = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        min_value=Decimal('0'),
        max_value=Decimal('100'),
    )
    final_grade = serializers.CharField(required=False, allow_blank=True, max_length=2)
    attendance_percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        min_value=Decimal('0'),
        max_value=Decimal('100'),
    )
    skills_covered = serializers.ListField(
        child=serializers.CharField(max_length=80),
        required=False,
        allow_empty=True,
    )

    def validate_enrollment_id(self, value):
        try:
            enrollment = Enrollment.objects.get(id=value)
        except Enrollment.DoesNotExist:
            raise serializers.ValidationError("Enrollment not found.")

        # Check if certificate already exists and is issued
        existing_cert = Certificate.objects.filter(
            student=enrollment.student,
            course=enrollment.course,
        ).exists()

        if existing_cert:
            raise serializers.ValidationError(
                "A certificate already exists for this student and course."
            )

        return value

    def validate(self, data):
        enrollment = Enrollment.objects.get(id=data['enrollment_id'])
        request = self.context.get('request')

        if request and request.user.role == 'instructor' and enrollment.instructor_id != request.user.id:
            raise serializers.ValidationError(
                "You can only issue certificates for your assigned learners."
            )

        final_score = data.get('final_score', calculate_final_score(enrollment))
        certificate_type = data.get('certificate_type', default_certificate_type(final_score))

        if certificate_type == Certificate.TYPE_EXCELLENCE and (
            final_score is None or Decimal(final_score) < Decimal('90')
        ):
            raise serializers.ValidationError(
                "Excellence certificates require an academy excellence score of at least 90%."
            )

        certificate = Certificate(
            student=enrollment.student,
            enrollment=enrollment,
            course=enrollment.course,
            completion_date=data['completion_date'],
        )

        if not certificate.is_eligible_for_certificate():
            raise serializers.ValidationError(
                "Student is not eligible for a certificate. "
                "Ensure enrollment is completed, student is approved, "
                "and all payments are settled."
            )

        return data

    def create(self, validated_data):
        enrollment = Enrollment.objects.get(id=validated_data['enrollment_id'])
        user = self.context['request'].user
        final_score = validated_data.get('final_score', calculate_final_score(enrollment))
        attendance_percentage = validated_data.get(
            'attendance_percentage',
            calculate_attendance_percentage(enrollment),
        )
        final_grade = (
            validated_data.get('final_grade')
            or grade_for_score(final_score)
        )
        certificate_type = validated_data.get(
            'certificate_type',
            default_certificate_type(final_score),
        )

        certificate, created = Certificate.objects.get_or_create(
            enrollment=enrollment,
            defaults={
                'student': enrollment.student,
                'course': enrollment.course,
                'completion_date': validated_data['completion_date'],
                'certificate_type': certificate_type,
                'final_score': final_score,
                'final_grade': final_grade,
                'attendance_percentage': attendance_percentage,
                'skills_covered': validated_data.get('skills_covered', []),
                'status': Certificate.STATUS_ACTIVE,
                'issued_by': user,
                'issued_at': timezone.now(),
                'issue_date': timezone.localdate(),
            }
        )

        if not created and certificate.status == Certificate.STATUS_DRAFT:
            certificate.status = Certificate.STATUS_ACTIVE
            certificate.issued_by = user
            certificate.issued_at = timezone.now()
            certificate.issue_date = timezone.localdate()
            certificate.completion_date = validated_data['completion_date']
            certificate.certificate_type = certificate_type
            certificate.final_score = final_score
            certificate.final_grade = final_grade
            certificate.attendance_percentage = attendance_percentage
            certificate.skills_covered = validated_data.get('skills_covered', [])
            certificate.save()

        return certificate


class PublicCertificateVerificationSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    programme_name = serializers.SerializerMethodField()
    specialization_title = serializers.CharField(source='course.title', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    issue_date = serializers.DateField(read_only=True)
    issued_by_name = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = [
            'certificate_number',
            'student_name',
            'programme_name',
            'specialization_title',
            'course_title',
            'issued_by_name',
            'issue_date',
            'certificate_type',
            'completion_date',
            'issued_at',
            'status',
            'status_label',
        ]

    def get_student_name(self, obj):
        names = [obj.student.first_name, obj.student.other_name, obj.student.last_name]
        return ' '.join(name for name in names if name)

    def get_programme_name(self, obj):
        return CERTIFICATE_PROGRAMME_NAME

    def get_issued_by_name(self, obj):
        return 'Velttech Academy'

    def get_status_label(self, obj):
        if obj.status == Certificate.STATUS_REVOKED:
            return 'Revoked'
        if obj.is_active():
            return 'Valid'
        return 'Draft'
