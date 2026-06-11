from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.http import FileResponse, HttpResponse
from django.db.models import Q

from .models import Certificate
from .serializers import (
    CertificateSerializer,
    CertificateListSerializer,
    CertificateIssuanceSerializer,
    PublicCertificateVerificationSerializer,
)
from .permissions import (
    CanIssueCertificate,
    CanViewCertificate,
    CanRevokeCertificate,
)


class CertificateViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing certificates.

    Endpoints:
    - GET /api/certificates/ - List certificates
    - GET /api/certificates/{id}/ - Get certificate details
    - POST /api/certificates/issue/ - Issue a new certificate
    - GET /api/certificates/{id}/download/ - Download certificate PDF
    - GET /api/certificates/{id}/revoke/ - Revoke certificate (admin only)
    - GET /api/certificates/verify/{code}/ - Verify certificate with code
    """

    queryset = Certificate.objects.all()
    permission_classes = [IsAuthenticated, CanViewCertificate]

    def get_serializer_class(self):
        if self.action == 'list':
            return CertificateListSerializer
        elif self.action == 'issue':
            return CertificateIssuanceSerializer
        elif self.action == 'verify':
            return PublicCertificateVerificationSerializer
        return CertificateSerializer

    def get_queryset(self):
        """Filter certificates based on user role"""
        user = self.request.user
        queryset = Certificate.objects.select_related(
            'student',
            'course',
            'enrollment',
            'enrollment__instructor',
            'issued_by',
        )

        certificate_status = self.request.query_params.get('status')
        course_id = self.request.query_params.get('course_id')
        student_id = self.request.query_params.get('student_id')

        if certificate_status:
            queryset = queryset.filter(status=certificate_status)
        if course_id:
            queryset = queryset.filter(course_id=course_id)
        if student_id:
            queryset = queryset.filter(student_id=student_id)

        if user.role == 'admin':
            return queryset

        if user.role == 'instructor':
            return queryset.filter(enrollment__instructor=user)

        if user.role == 'student':
            return queryset.filter(student__user=user)

        if user.role == 'parent':
            return queryset.filter(student__parent__user=user)

        return Certificate.objects.none()

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def issue(self, request):
        """Issue a new certificate"""
        self.permission_classes = [IsAuthenticated, CanIssueCertificate]
        self.check_permissions(request)

        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        certificate = serializer.save()

        # Generate PDF
        try:
            from .pdf_generator import CertificatePDFGenerator

            generator = CertificatePDFGenerator(certificate)
            generator.save_to_certificate()
        except Exception as e:
            return Response(
                {'error': f'Failed to generate certificate PDF: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            CertificateSerializer(certificate).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        """Download certificate PDF"""
        certificate = self.get_object()

        if not certificate.certificate_file:
            return Response(
                {'error': 'Certificate file not available'},
                status=status.HTTP_404_NOT_FOUND
            )

        return FileResponse(
            certificate.certificate_file.open('rb'),
            as_attachment=True,
            filename=f"{certificate.certificate_number}.pdf"
        )

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def revoke(self, request, pk=None):
        """Revoke a certificate (admin only)"""
        self.permission_classes = [IsAuthenticated, CanRevokeCertificate]
        self.check_permissions(request)

        certificate = self.get_object()
        reason = request.data.get('reason', '')

        if certificate.revoke(reason):
            return Response(
                CertificateSerializer(certificate).data,
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {'error': 'Certificate cannot be revoked (only issued certificates can be revoked)'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(
        detail=False,
        methods=['get'],
        permission_classes=[AllowAny],
        url_path=r'verify/(?P<verification_code>[^/.]+)',
    )
    def verify(self, request, verification_code=None):
        """
        Verify certificate using verification code.
        Public endpoint - no authentication required.
        """
        code = verification_code or request.query_params.get('code')
        if not code:
            return Response(
                {'error': 'Verification code is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        certificate = get_object_or_404(
            Certificate.objects.select_related('student', 'course'),
            verification_code=code,
        )

        serializer = self.get_serializer(certificate)
        return Response(serializer.data)


class CertificateEligibilityListView(generics.ListAPIView):
    """
    List students eligible for certificate in a specific course.
    Only accessible to admins and course instructors.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = CertificateListSerializer

    def get_queryset(self):
        """Get eligible students for course"""
        from enrollments.models import Enrollment

        user = self.request.user
        course_id = self.request.query_params.get('course_id')

        if not course_id:
            return Certificate.objects.none()

        # Get all completed enrollments for the course
        completed_enrollments = Enrollment.objects.select_related(
            'student',
            'course',
            'instructor',
        ).filter(
            course_id=course_id,
            status=Enrollment.STATUS_COMPLETED,
        )

        # Filter by user role
        if user.role == 'admin':
            return completed_enrollments
        elif user.role == 'instructor':
            return completed_enrollments.filter(instructor=user)
        else:
            return Enrollment.objects.none()

    def list(self, request, *args, **kwargs):
        """Return list of eligible students (not certificates)"""
        from enrollments.models import Enrollment
        from students.serializers import StudentSerializer

        queryset = self.get_queryset()
        eligible_students = []

        for enrollment in queryset:
            # Check if already has issued certificate
            has_issued = Certificate.objects.filter(
                enrollment=enrollment,
                status=Certificate.STATUS_ISSUED,
            ).exists()

            certificate_probe = Certificate(
                student=enrollment.student,
                enrollment=enrollment,
                course=enrollment.course,
                completion_date=enrollment.end_date or enrollment.updated_at.date(),
            )

            if not has_issued and certificate_probe.is_eligible_for_certificate():
                eligible_students.append({
                    'id': enrollment.student.id,
                    'enrollment_id': enrollment.id,
                    'name': self._get_student_name(enrollment.student),
                    'email': enrollment.student.email,
                    'status': enrollment.student.approval_status,
                    'enrollment_status': enrollment.status,
                    'course_title': enrollment.course.title,
                })

        return Response(eligible_students)

    def _get_student_name(self, student):
        names = [student.first_name, student.other_name, student.last_name]
        return ' '.join(name for name in names if name)
