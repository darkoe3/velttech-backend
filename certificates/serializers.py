from rest_framework import serializers
from django.utils import timezone

from .models import Certificate
from students.models import Student
from enrollments.models import Enrollment
from courses.models import Course


class CertificateSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
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
            'course_title',
            'issued_by',
            'issued_by_name',
            'issued_at',
            'completion_date',
            'status',
            'verification_code',
            'revoked_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'certificate_number',
            'issued_at',
            'verification_code',
            'created_at',
            'updated_at',
        ]

    def get_student_name(self, obj):
        names = [obj.student.first_name, obj.student.other_name, obj.student.last_name]
        return ' '.join(name for name in names if name)

    def get_issued_by_name(self, obj):
        if obj.issued_by:
            return f"{obj.issued_by.first_name} {obj.issued_by.last_name}"
        return "Velttech Academy"


class CertificateListSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='course.title', read_only=True)

    class Meta:
        model = Certificate
        fields = [
            'id',
            'certificate_number',
            'student',
            'student_name',
            'course_title',
            'status',
            'completion_date',
            'issued_at',
            'verification_code',
        ]

    def get_student_name(self, obj):
        names = [obj.student.first_name, obj.student.other_name, obj.student.last_name]
        return ' '.join(name for name in names if name)


class CertificateIssuanceSerializer(serializers.Serializer):
    """Serializer for issuing certificates"""
    enrollment_id = serializers.IntegerField()
    completion_date = serializers.DateField()

    def validate_enrollment_id(self, value):
        try:
            enrollment = Enrollment.objects.get(id=value)
        except Enrollment.DoesNotExist:
            raise serializers.ValidationError("Enrollment not found.")

        # Check if certificate already exists and is issued
        existing_cert = Certificate.objects.filter(
            enrollment=enrollment,
            status=Certificate.STATUS_ISSUED,
        ).exists()

        if existing_cert:
            raise serializers.ValidationError(
                "An issued certificate already exists for this enrollment."
            )

        return value

    def validate(self, data):
        enrollment = Enrollment.objects.get(id=data['enrollment_id'])
        request = self.context.get('request')

        if request and request.user.role == 'instructor' and enrollment.instructor_id != request.user.id:
            raise serializers.ValidationError(
                "You can only issue certificates for your assigned learners."
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

        certificate, created = Certificate.objects.get_or_create(
            enrollment=enrollment,
            defaults={
                'student': enrollment.student,
                'course': enrollment.course,
                'completion_date': validated_data['completion_date'],
                'status': Certificate.STATUS_ISSUED,
                'issued_by': user,
                'issued_at': timezone.now(),
            }
        )

        if not created and certificate.status == Certificate.STATUS_DRAFT:
            certificate.status = Certificate.STATUS_ISSUED
            certificate.issued_by = user
            certificate.issued_at = timezone.now()
            certificate.save()

        return certificate


class PublicCertificateVerificationSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    course_title = serializers.CharField(source='course.title', read_only=True)

    class Meta:
        model = Certificate
        fields = [
            'certificate_number',
            'student_name',
            'course_title',
            'completion_date',
            'issued_at',
            'status',
        ]

    def get_student_name(self, obj):
        names = [obj.student.first_name, obj.student.other_name, obj.student.last_name]
        return ' '.join(name for name in names if name)
