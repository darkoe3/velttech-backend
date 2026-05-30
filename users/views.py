from datetime import date
from decimal import Decimal
import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.db.models.functions import ExtractMonth
from django.db.models import Count, Prefetch, Q, Sum
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from courses.models import Course
from enrollments.models import (
    Assignment,
    AssignmentSubmission,
    Attendance,
    Enrollment,
    LessonNote,
    ProgressReport,
)
from notifications.models import Notification
from payments.models import Payment
from payments.serializers import PaymentHistorySerializer
from students.models import Parent, Student
from students.serializers import MyChildSerializer

from .models import ActivityLog
from .serializers import (
    ActivityLogSerializer,
    ApprovalAwareTokenRefreshSerializer,
    DashboardAttendanceSerializer,
    DashboardChildSerializer,
    DashboardCourseSerializer,
    DashboardNotificationSerializer,
    DashboardPaymentSerializer,
    DashboardProgressReportSerializer,
    EmailTokenObtainPairSerializer,
    InstructorCourseSerializer,
    InstructorEnrollmentSerializer,
    InstructorStudentSerializer,
    RecentRegistrationSerializer,
    RegisterSerializer,
    ChangePasswordSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PendingAccountSerializer,
    UserSerializer,
)
from enrollments.serializers import (
    AssignmentSerializer,
    AssignmentSubmissionSerializer,
    AttendanceSerializer,
    EnrollmentSerializer,
    LessonNoteSerializer,
    GradeAssignmentSubmissionSerializer,
    MyAssignmentSerializer,
    ProgressReportSerializer,
)

User = get_user_model()
logger = logging.getLogger(__name__)


class IsAdminUserRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.ROLE_ADMIN
        )


class IsInstructorUserRole(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == User.ROLE_INSTRUCTOR
        )


def signup_rate_key(kind, value):
    clean_value = ''.join(char if char.isalnum() else '_' for char in (value or '').lower())
    return f'signup-rate:{kind}:{clean_value[:120]}'


def bump_signup_attempt(key, timeout=600):
    if not key:
        return 0
    if cache.add(key, 1, timeout=timeout):
        return 1
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=timeout)
        return 1


class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = RegisterSerializer
    max_signup_attempts = 3

    def get_serializer_context(self):
        context = super().get_serializer_context()
        repeated_attempts = getattr(self.request, '_request_signup_attempts', 1) > 1
        context['suspicious_reasons'] = ['repeated signup attempts'] if repeated_attempts else []
        return context

    def create(self, request, *args, **kwargs):
        email = (request.data.get('email') or '').strip().lower()
        ip_address = client_ip(request) or 'unknown'
        attempt_counts = [
            bump_signup_attempt(signup_rate_key('ip', ip_address)),
        ]
        if email:
            attempt_counts.append(bump_signup_attempt(signup_rate_key('email', email)))
        request._request_signup_attempts = max(attempt_counts)

        if request._request_signup_attempts > self.max_signup_attempts:
            return Response(
                {'detail': 'Too many signup attempts. Please try again later.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        response = super().create(request, *args, **kwargs)
        response.data = {
            'detail': 'Your account has been submitted successfully and is awaiting admin approval.',
            'pending_approval': True,
        }
        return response

    def perform_create(self, serializer):
        user = serializer.save()
        student = getattr(user, 'student_profile', None)
        if user.role == User.ROLE_STUDENT and student and is_adult_learner(student):
            try:
                send_adult_signup_pending_email(student)
            except Exception:
                logger.exception('Could not send pending approval email for adult learner %s.', student.pk)


class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = EmailTokenObtainPairSerializer


class RefreshView(TokenRefreshView):
    permission_classes = [permissions.AllowAny]
    serializer_class = ApprovalAwareTokenRefreshSerializer


class LogoutView(generics.GenericAPIView):
    def post(self, request, *args, **kwargs):
        refresh = request.data.get('refresh')
        if refresh:
            RefreshToken(refresh).blacklist()
        return Response({'detail': 'Logged out.'})


class MeView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class ChangePasswordView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ChangePasswordSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save(update_fields=['password'])
        return Response({'detail': 'Password changed successfully.'})


class PasswordResetRequestView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data['email']).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_link = f'{settings.FRONTEND_URL.rstrip("/")}/reset-password?uid={uid}&token={token}'
            try:
                send_mail(
                    subject='Reset your Velttech Academy password',
                    message=(
                        'We received a request to reset your Velttech Academy password.\n\n'
                        f'Reset link: {reset_link}\n\n'
                        'If you did not request this, you can ignore this email.'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception:
                logger.exception('Could not send password reset email for user %s.', user.pk)
        return Response({'detail': 'If this email exists, a password reset link has been sent.'})


class PasswordResetConfirmView(generics.GenericAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user_id = force_str(urlsafe_base64_decode(serializer.validated_data['uid']))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({'detail': 'Invalid password reset link.'}, status=400)
        if not default_token_generator.check_token(user, serializer.validated_data['token']):
            return Response({'detail': 'Invalid or expired password reset token.'}, status=400)
        user.set_password(serializer.validated_data['new_password'])
        user.save(update_fields=['password'])
        return Response({'detail': 'Password reset successfully.'})


def client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR')


def log_admin_action(request, action, description):
    ActivityLog.objects.create(
        user=request.user if request.user.is_authenticated else None,
        role=getattr(request.user, 'role', ''),
        action=action,
        description=description,
        ip_address=client_ip(request),
    )


def student_course_summary(student):
    course_titles = [
        enrollment.course.title
        for enrollment in student.enrollments.select_related('course').all()
    ]
    return ', '.join(course_titles) if course_titles else 'To be assigned by the academy'


def course_invoice_fee(course):
    fee = getattr(course, 'fee', None)
    if fee:
        return fee
    return getattr(course, 'monthly_fee', Decimal('0.00')) or Decimal('0.00')


def create_pending_invoice_for_enrollment(enrollment):
    enrollment = Enrollment.objects.select_related(
        'student',
        'student__parent',
        'course',
    ).select_for_update().get(pk=enrollment.pk)
    existing_payment = Payment.objects.filter(
        enrollment__student=enrollment.student,
        enrollment__course=enrollment.course,
        status__in=[Payment.STATUS_PENDING, Payment.STATUS_PAID],
    ).first()
    if existing_payment:
        return existing_payment, False

    today = timezone.localdate()
    payment = Payment.objects.create(
        enrollment=enrollment,
        amount=course_invoice_fee(enrollment.course),
        payment_method=Payment.METHOD_PENDING,
        status=Payment.STATUS_PENDING,
        month=today.month,
        year=today.year,
        notes='Automatically generated when student was approved or enrolled.',
    )
    return payment, True


def approval_invoice_for_student(student):
    enrollment = student.enrollments.select_related('course').order_by('-created_at').first()
    if not enrollment:
        return None, False
    with transaction.atomic():
        return create_pending_invoice_for_enrollment(enrollment)


def ensure_adult_programme_enrollment(student):
    if not is_adult_learner(student) or not student.programme_of_interest:
        return None, False
    course = Course.objects.filter(
        title__iexact=student.programme_of_interest,
        is_active=True,
    ).first() or Course.objects.filter(title__iexact=student.programme_of_interest).first()
    if not course:
        return None, False
    enrollment, created = Enrollment.objects.get_or_create(
        student=student,
        course=course,
        defaults={'status': Enrollment.STATUS_PENDING},
    )
    return enrollment, created


def format_invoice_amount(payment):
    return f'GHS {payment.amount:,.2f}' if payment else 'GHS 0.00'


def is_adult_learner(student):
    return student.learner_type == Student.LEARNER_ADULT or (student.user_id and not student.parent_id)


def student_contact_email(student):
    if is_adult_learner(student):
        return student.email or (student.user.email if student.user else '')
    if student.parent and student.parent.email:
        return student.parent.email
    if student.parent and student.parent.user:
        return student.parent.user.email
    return student.email or (student.user.email if student.user else '')


def send_adult_signup_pending_email(student):
    email = student_contact_email(student)
    if not email:
        return False
    programme = student.programme_of_interest or 'To be confirmed'
    send_mail(
        subject='Your Velttech Academy Signup Is Pending Approval',
        message=(
            f'Dear {student},\n\n'
            'We have received your Velttech Academy signup.\n\n'
            f'Programme of interest: {programme}\n'
            'Status: Pending admin approval\n\n'
            'You will be notified once your account has been approved. '
            'You will be able to access your student dashboard after approval.\n\n'
            'Contact:\n'
            'Email: info@velttech.org\n'
            'Phone: +233 55 510 6820\n\n'
            'Velttech Coding Academy\n'
            'Website: https://velttech.org\n'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )
    return True


def send_parent_account_approval_email(user):
    send_mail(
        subject='Welcome to Velttech Coding Academy',
        message=(
            f'Dear {user.first_name},\n\n'
            'Welcome to Velttech Coding Academy.\n\n'
            'Your parent account has been approved. You can now log in to your parent portal, '
            'add or manage child records, and follow academy updates.\n\n'
            'Login link: https://velttech.org/login\n\n'
            'Contact:\n'
            'Email: info@velttech.org\n'
            'Phone: +233 55 510 6820\n\n'
            'Velttech Coding Academy\n'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    return True


def send_account_approval_email(user):
    student = getattr(user, 'student_profile', None)
    if user.role == User.ROLE_STUDENT and student:
        return send_student_approval_email(student)
    return send_parent_account_approval_email(user)


def send_student_approval_email(student, payment=None):
    recipient_email = student_contact_email(student)
    if not recipient_email:
        return False

    adult = is_adult_learner(student)
    recipient_name = str(student) if adult else str(student.parent)
    learner_name = str(student)
    course_summary = payment.enrollment.course.title if payment else student_course_summary(student)
    course_fee = format_invoice_amount(payment) if payment else 'To be confirmed by the academy'
    approval_line = (
        'Your adult learner account has been approved for Velttech Coding Academy.'
        if adult else f'Your child, {learner_name}, has been approved for Velttech Coding Academy.'
    )
    portal_label = 'student portal' if adult else 'parent portal'
    message = (
        f'Dear {recipient_name},\n\n'
        f'{approval_line}\n\n'
        f'Approved course: {course_summary}\n\n'
        f'Course fee: {course_fee}\n'
        'Login link: https://velttech.org/login\n\n'
        f'Please log in to your {portal_label} to complete payment.\n'
    )
    if payment:
        message += (
            f'Invoice amount: {format_invoice_amount(payment)}\n'
            'Payment status: Pending\n'
            'Click Pay Now in your dashboard to complete payment.\n'
            'Payment portal: https://velttech.org/payments\n\n'
        )
    message += (
        'Contact:\n'
        'Email: info@velttech.org\n'
        'Phone: +233 55 510 6820\n\n'
        'Velttech Coding Academy\n'
        'Website: https://velttech.org\n'
    )
    send_mail(
        subject='Your Velttech Coding Academy Enrollment Has Been Approved'
        if adult else 'Your Child Has Been Approved - Velttech Coding Academy',
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient_email],
        fail_silently=False,
    )
    return True


def send_admin_invoice_notification(student, payment):
    if not payment:
        return False
    parent = student.parent
    message = (
        'A student has been approved and an invoice has been created.\n\n'
        f'Learner type: {"Adult learner" if is_adult_learner(student) else "Child learner"}\n'
        f'Parent: {parent or "Not provided"}\n'
        f'Parent email: {parent.email if parent else "Not provided"}\n'
        f'Learner: {student}\n'
        f'Course: {payment.enrollment.course.title}\n'
        f'Amount: {format_invoice_amount(payment)}\n'
        f'Payment status: {payment.status.title()}\n'
    )
    send_mail(
        subject='New Student Approved and Invoice Created',
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=['info@velttech.org'],
        fail_silently=False,
    )
    return True


def visible_notifications_for(user):
    if user.role == User.ROLE_ADMIN:
        return Notification.objects.all()

    audience_map = {
        User.ROLE_PARENT: Notification.AUDIENCE_PARENTS,
        User.ROLE_STUDENT: Notification.AUDIENCE_STUDENTS,
        User.ROLE_INSTRUCTOR: Notification.AUDIENCE_INSTRUCTORS,
    }

    return Notification.objects.filter(
        is_active=True,
        audience__in=[Notification.AUDIENCE_ALL, audience_map.get(user.role)],
    ).filter(Q(recipient__isnull=True) | Q(recipient=user))


def enforce_student_approved(user):
    if user.approval_status == User.APPROVAL_PENDING:
        raise PermissionDenied(
            'Your account is pending admin approval. You will be notified once approved.'
        )
    if user.approval_status == User.APPROVAL_REJECTED:
        raise PermissionDenied('Your account was not approved. Please contact Velttech Coding Academy.')
    if user.role != User.ROLE_STUDENT:
        return
    student = getattr(user, 'student_profile', None)
    if student and student.approval_status == Student.STATUS_PENDING:
        raise PermissionDenied(
            'Your account is pending admin approval. You will be notified once approved.'
        )
    if student and student.approval_status == Student.STATUS_REJECTED:
        raise PermissionDenied('Your account was not approved. Please contact Velttech Coding Academy.')


def visible_courses_for(user):
    queryset = Course.objects.all()
    if user.role == User.ROLE_ADMIN:
        return queryset
    if user.role == User.ROLE_PARENT:
        return queryset.filter(enrollments__student__parent__user=user).distinct()
    if user.role == User.ROLE_STUDENT:
        return queryset.filter(enrollments__student__user=user).distinct()
    if user.role == User.ROLE_INSTRUCTOR:
        return queryset.filter(enrollments__instructor=user).distinct()
    return queryset.none()


def visible_payments_for(user):
    queryset = Payment.objects.select_related(
        'enrollment',
        'enrollment__student',
        'enrollment__course',
    )
    if user.role == User.ROLE_ADMIN:
        return queryset
    if user.role == User.ROLE_PARENT:
        return queryset.filter(enrollment__student__parent__user=user)
    if user.role == User.ROLE_STUDENT:
        return queryset.filter(enrollment__student__user=user)
    if user.role == User.ROLE_INSTRUCTOR:
        return queryset.filter(enrollment__instructor=user)
    return queryset.none()


class DashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        enforce_student_approved(user)
        notifications = visible_notifications_for(user)[:5]

        if user.role == User.ROLE_ADMIN:
            recent_registrations = User.objects.order_by('-date_joined')[:5]
            recent_payments = visible_payments_for(user).order_by('-created_at')[:5]
            today = timezone.localdate()
            paid_payments = Payment.objects.filter(status=Payment.STATUS_PAID)
            monthly = paid_payments.annotate(
                month_number=ExtractMonth('created_at')
            ).values('month_number').annotate(total=Sum('amount')).order_by('month_number')
            total_paid_amount = paid_payments.aggregate(total=Sum('amount'))['total'] or 0
            current_month_revenue = paid_payments.filter(
                created_at__year=today.year,
                created_at__month=today.month,
            ).aggregate(total=Sum('amount'))['total'] or 0
            month_names = ['January','February','March','April','May','June','July','August','September','October','November','December']
            return Response(
                {
                    'role': user.role,
                    'summary': {
                        'total_students': Student.objects.count(),
                        'approved_students': Student.objects.filter(approval_status=Student.STATUS_APPROVED).count(),
                        'pending_approvals': Student.objects.filter(approval_status=Student.STATUS_PENDING).count(),
                        'pending_accounts': User.objects.filter(
                            approval_status=User.APPROVAL_PENDING,
                            role__in=[User.ROLE_PARENT, User.ROLE_STUDENT],
                        ).count(),
                        'total_parents': Parent.objects.count(),
                        'total_courses': Course.objects.count(),
                        'total_enrollments': Enrollment.objects.count(),
                        'total_payments': Payment.objects.count(),
                        'total_paid_amount': total_paid_amount,
                        'current_month_revenue': current_month_revenue,
                        'pending_payments': Payment.objects.filter(status=Payment.STATUS_PENDING).count(),
                        'total_instructors': User.objects.filter(role=User.ROLE_INSTRUCTOR).count(),
                    },
                    'pending_children': DashboardChildSerializer(
                        Student.objects.filter(approval_status=Student.STATUS_PENDING)
                        .prefetch_related('enrollments__course')
                        .distinct()[:5],
                        many=True,
                    ).data,
                    'pending_accounts': PendingAccountSerializer(
                        User.objects.filter(
                            approval_status=User.APPROVAL_PENDING,
                            role__in=[User.ROLE_PARENT, User.ROLE_STUDENT],
                        ).select_related('parent_profile', 'student_profile')[:5],
                        many=True,
                    ).data,
                    'approved_unassigned_children': DashboardChildSerializer(
                        Student.objects.filter(
                            approval_status=Student.STATUS_APPROVED,
                            enrollments__isnull=True,
                        )
                        .prefetch_related('enrollments__course')
                        .distinct()[:5],
                        many=True,
                    ).data,
                    'recent_registrations': RecentRegistrationSerializer(
                        recent_registrations,
                        many=True,
                    ).data,
                    'recent_payments': DashboardPaymentSerializer(
                        recent_payments,
                        many=True,
                    ).data,
                    'notifications': DashboardNotificationSerializer(
                        notifications,
                        many=True,
                    ).data,
                    'instructors': UserSerializer(
                        User.objects.filter(role=User.ROLE_INSTRUCTOR),
                        many=True,
                    ).data,
                    'monthly_payment_totals': [
                        {'month': month_names[item['month_number'] - 1], 'total': item['total'] or 0}
                        for item in monthly if item['month_number']
                    ],
                    'enrollment_status_counts': [
                        {'status': item['status'], 'count': item['count']}
                        for item in Enrollment.objects.values('status').annotate(count=Count('id'))
                    ],
                    'student_approval_status_counts': [
                        {'status': item['approval_status'], 'count': item['count']}
                        for item in Student.objects.values('approval_status').annotate(count=Count('id'))
                    ],
                    'course_enrollment_counts': [
                        {'course': item['course__title'], 'count': item['count']}
                        for item in Enrollment.objects.values('course__title').annotate(count=Count('id'))
                    ],
                    'latest_activity_logs': ActivityLogSerializer(
                        ActivityLog.objects.select_related('user')[:6],
                        many=True,
                    ).data,
                }
            )

        if user.role == User.ROLE_PARENT:
            children = Student.objects.filter(parent__user=user).prefetch_related(
                'enrollments__course'
            )
            payments = visible_payments_for(user)
            payment_summary = payments.aggregate(
                total=Count('id'),
                completed=Count('id', filter=Q(status=Payment.STATUS_PAID)),
                pending=Count('id', filter=Q(status=Payment.STATUS_PENDING)),
                completed_amount=Sum(
                    'amount',
                    filter=Q(status=Payment.STATUS_PAID),
                ),
                outstanding_amount=Sum(
                    'amount',
                    filter=Q(status=Payment.STATUS_PENDING),
                ),
            )
            pending_payment_ids = list(
                payments.filter(status=Payment.STATUS_PENDING).values_list('id', flat=True)
            )
            payment_dashboard = build_parent_payment_dashboard(children, payments)
            serialized_children = DashboardChildSerializer(children, many=True).data
            for child in serialized_children:
                child.update(payment_dashboard['child_statuses'].get(child['id'], {}))
            return Response(
                {
                    'role': user.role,
                    'children': serialized_children,
                    'payment_summary': {
                        'total': payment_summary['total'] or 0,
                        'completed': payment_summary['completed'] or 0,
                        'pending': payment_summary['pending'] or 0,
                        'completed_amount': payment_summary['completed_amount'] or 0,
                        'outstanding_amount': payment_summary['outstanding_amount'] or 0,
                        'pending_payment_ids': pending_payment_ids,
                        'current_payment_period': payment_dashboard['current_payment_period'],
                        'current_pending_payment_ids': payment_dashboard['current_pending_payment_ids'],
                        'outstanding_monthly_payment': payment_dashboard['outstanding_monthly_payment'],
                        'current_amount_paid': payment_dashboard['current_amount_paid'],
                        'last_payment': payment_dashboard['last_payment'],
                    },
                    'recent_payments': DashboardPaymentSerializer(
                        payments.order_by('-created_at')[:5],
                        many=True,
                    ).data,
                    'notifications': DashboardNotificationSerializer(
                        notifications,
                        many=True,
                    ).data,
                }
            )

        if user.role == User.ROLE_STUDENT:
            attendance = Attendance.objects.filter(
                enrollment__student__user=user,
            ).select_related('enrollment__course')
            progress_reports = ProgressReport.objects.filter(
                enrollment__student__user=user,
            ).select_related('enrollment__course')
            payments = visible_payments_for(user)
            payment_summary = payments.aggregate(
                total=Count('id'),
                completed=Count('id', filter=Q(status=Payment.STATUS_PAID)),
                pending=Count('id', filter=Q(status=Payment.STATUS_PENDING)),
                completed_amount=Sum(
                    'amount',
                    filter=Q(status=Payment.STATUS_PAID),
                ),
                outstanding_amount=Sum(
                    'amount',
                    filter=Q(status=Payment.STATUS_PENDING),
                ),
            )
            pending_payment_ids = list(
                payments.filter(status=Payment.STATUS_PENDING).values_list('id', flat=True)
            )
            assignments = Assignment.objects.filter(
                is_active=True,
                course__enrollments__student__user=user,
            ).distinct()
            student_profile = getattr(user, 'student_profile', None)
            latest_enrollment = Enrollment.objects.filter(
                student__user=user,
            ).select_related('course').order_by('-created_at').first()
            return Response(
                {
                    'role': user.role,
                    'learner_type': Student.LEARNER_ADULT,
                    'selected_programme': (
                        student_profile.programme_of_interest
                        if student_profile and student_profile.programme_of_interest
                        else (latest_enrollment.course.title if latest_enrollment else '')
                    ),
                    'enrollment_status': latest_enrollment.status if latest_enrollment else 'pending',
                    'courses': DashboardCourseSerializer(
                        visible_courses_for(user),
                        many=True,
                    ).data,
                    'notifications': DashboardNotificationSerializer(
                        notifications,
                        many=True,
                    ).data,
                    'attendance_summary': {
                        'total': attendance.count(),
                        'present': attendance.filter(status=Attendance.STATUS_PRESENT).count(),
                        'absent': attendance.filter(status=Attendance.STATUS_ABSENT).count(),
                        'late': attendance.filter(status=Attendance.STATUS_LATE).count(),
                        'excused': attendance.filter(status=Attendance.STATUS_EXCUSED).count(),
                    },
                    'recent_attendance': DashboardAttendanceSerializer(
                        attendance.order_by('-date', '-created_at')[:5],
                        many=True,
                    ).data,
                    'latest_progress_report': DashboardProgressReportSerializer(
                        progress_reports.first(),
                    ).data if progress_reports.exists() else None,
                    'assignment_summary': {
                        'total': assignments.count(),
                        'submitted': AssignmentSubmission.objects.filter(
                            assignment__in=assignments,
                            student__user=user,
                            status__in=[
                                AssignmentSubmission.STATUS_SUBMITTED,
                                AssignmentSubmission.STATUS_GRADED,
                            ],
                        ).count(),
                    },
                    'payment_summary': {
                        'total': payment_summary['total'] or 0,
                        'completed': payment_summary['completed'] or 0,
                        'pending': payment_summary['pending'] or 0,
                        'completed_amount': payment_summary['completed_amount'] or 0,
                        'outstanding_amount': payment_summary['outstanding_amount'] or 0,
                        'pending_payment_ids': pending_payment_ids,
                    },
                    'recent_payments': DashboardPaymentSerializer(
                        payments.order_by('-created_at')[:5],
                        many=True,
                    ).data,
                }
            )

        if user.role == User.ROLE_INSTRUCTOR:
            assigned_enrollments = Enrollment.objects.select_related(
                'student',
                'course',
            ).filter(instructor=user)
            return Response(
                {
                    'role': user.role,
                    'courses': DashboardCourseSerializer(
                        visible_courses_for(user),
                        many=True,
                    ).data,
                    'assigned_students': DashboardChildSerializer(
                        Student.objects.filter(enrollments__instructor=user)
                        .prefetch_related('enrollments__course')
                        .distinct(),
                        many=True,
                    ).data,
                    'assigned_enrollments': assigned_enrollments.count(),
                    'notifications': DashboardNotificationSerializer(
                        notifications,
                        many=True,
                    ).data,
                }
            )

        return Response(
            {
                'role': user.role,
                'notifications': DashboardNotificationSerializer(
                    notifications,
                    many=True,
                ).data,
            }
        )


class MyCoursesView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DashboardCourseSerializer

    def get_queryset(self):
        enforce_student_approved(self.request.user)
        return visible_courses_for(self.request.user)


class MyChildrenView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DashboardChildSerializer

    def get_queryset(self):
        user = self.request.user
        enforce_student_approved(user)
        if user.role == User.ROLE_ADMIN:
            return Student.objects.prefetch_related('enrollments__course')
        if user.role == User.ROLE_PARENT:
            return Student.objects.filter(parent__user=user).prefetch_related(
                'enrollments__course'
            )
        return Student.objects.none()

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return MyChildSerializer
        return super().get_serializer_class()

    def perform_create(self, serializer):
        user = self.request.user
        enforce_student_approved(user)
        if user.role != User.ROLE_PARENT:
            raise PermissionDenied('Only parents can create children.')
        parent_profile = getattr(user, 'parent_profile', None)
        if not parent_profile:
            raise PermissionDenied('Parent profile is required before adding children.')
        serializer.save(parent=parent_profile)


class MyPaymentsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = DashboardPaymentSerializer

    def get_queryset(self):
        enforce_student_approved(self.request.user)
        return visible_payments_for(self.request.user)


def month_sequence(start_date, end_date):
    current = start_date.replace(day=1)
    final = end_date.replace(day=1)
    while current <= final:
        yield current
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)


PAYMENT_PERIOD_MONTHS = [
    '',
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
]


def payment_period_label(payment, year, month):
    if payment and payment.payment_period:
        return payment.payment_period
    if month and year and 1 <= month <= 12:
        return f'{PAYMENT_PERIOD_MONTHS[month]} {year}'
    return str(year) if year else ''


def payment_period_for_payment(payment):
    payment_day = payment.payment_date or (
        payment.paid_at.date() if payment.paid_at else payment.created_at.date()
    )
    return payment_period_label(
        payment,
        payment.year or payment_day.year,
        payment.month or payment_day.month,
    )


def build_parent_payment_dashboard(children, payments):
    today = timezone.localdate()
    current_period = payment_period_label(None, today.year, today.month)
    current_payments = payments.filter(
        Q(month=today.month, year=today.year)
        | Q(payment_date__year=today.year, payment_date__month=today.month)
        | Q(paid_at__year=today.year, paid_at__month=today.month)
        | Q(month__isnull=True, year__isnull=True, created_at__year=today.year, created_at__month=today.month)
    )
    current_pending = current_payments.filter(status=Payment.STATUS_PENDING)
    current_paid = current_payments.filter(status=Payment.STATUS_PAID)
    latest_payment = payments.filter(status=Payment.STATUS_PAID).order_by('-paid_at', '-payment_date', '-created_at').first()

    child_statuses = {}
    for child in children:
        child_current = current_payments.filter(enrollment__student_id=child.id)
        child_pending = child_current.filter(status=Payment.STATUS_PENDING)
        child_paid = child_current.filter(status=Payment.STATUS_PAID)
        child_statuses[child.id] = {
            'current_payment_status': (
                'pending'
                if child_pending.exists()
                else ('paid' if child_paid.exists() else 'no outstanding payment')
            ),
            'current_payment_period': current_period,
            'outstanding_amount': child_pending.aggregate(total=Sum('amount'))['total'] or Decimal('0.00'),
            'pending_payment_ids': list(child_pending.values_list('id', flat=True)),
        }

    return {
        'current_payment_period': current_period,
        'current_pending_payment_ids': list(current_pending.values_list('id', flat=True)),
        'outstanding_monthly_payment': current_pending.aggregate(total=Sum('amount'))['total'] or Decimal('0.00'),
        'current_amount_paid': current_paid.aggregate(total=Sum('amount'))['total'] or Decimal('0.00'),
        'last_payment': {
            'amount': latest_payment.amount,
            'payment_period': payment_period_for_payment(latest_payment),
            'paid_at': latest_payment.paid_at,
            'student_name': str(latest_payment.enrollment.student),
            'course_title': latest_payment.enrollment.course.title,
        } if latest_payment else None,
        'child_statuses': child_statuses,
    }


def build_payment_history_rows(enrollments):
    today = timezone.localdate()
    rows = []
    enrollment_ids = [enrollment.id for enrollment in enrollments]
    payments = Payment.objects.filter(enrollment_id__in=enrollment_ids)

    payments_by_period = {}
    for payment in payments:
        payment_day = payment.payment_date or (
            payment.paid_at.date() if payment.paid_at else payment.created_at.date()
        )
        month = payment.month or payment_day.month
        year = payment.year or payment_day.year
        payments_by_period.setdefault((payment.enrollment_id, year, month), []).append(payment)

    for enrollment in enrollments:
        start = enrollment.start_date or enrollment.enrolled_at
        end = enrollment.end_date or today
        if end < start:
            end = start

        for period in month_sequence(start, min(end, today)):
            period_payments = payments_by_period.get((enrollment.id, period.year, period.month), [])
            paid_payments = [
                payment
                for payment in period_payments
                if payment.status == Payment.STATUS_PAID
            ]
            expected_amount = course_invoice_fee(enrollment.course)
            amount_paid = sum(
                (payment.amount for payment in paid_payments),
                Decimal('0.00'),
            )
            balance = max(expected_amount - amount_paid, Decimal('0.00'))

            latest_payment = sorted(
                period_payments,
                key=lambda item: item.payment_date
                or (item.paid_at.date() if item.paid_at else item.created_at.date()),
                reverse=True,
            )[0] if period_payments else None

            if latest_payment and latest_payment.status in [Payment.STATUS_PENDING, Payment.STATUS_FAILED]:
                payment_status = latest_payment.status
            elif expected_amount == 0 and not paid_payments:
                payment_status = 'unpaid'
            elif amount_paid >= expected_amount:
                payment_status = 'paid'
            elif amount_paid > 0:
                payment_status = 'partial'
            else:
                payment_status = 'unpaid'

            rows.append(
                {
                    'id': latest_payment.id if latest_payment else None,
                    'student_id': enrollment.student_id,
                    'student_name': str(enrollment.student),
                    'parent_name': str(enrollment.student.parent) if enrollment.student.parent else '',
                    'parent_phone': enrollment.student.parent.phone_number if enrollment.student.parent else '',
                    'course_title': enrollment.course.title,
                    'month': period.month,
                    'year': period.year,
                    'payment_period': payment_period_label(latest_payment, period.year, period.month),
                    'expected_amount': expected_amount,
                    'amount_paid': amount_paid,
                    'balance': balance,
                    'payment_status': payment_status,
                    'payment_method': latest_payment.payment_method if latest_payment else '',
                    'reference': latest_payment.transaction_reference if latest_payment and latest_payment.transaction_reference else '',
                    'payment_date': (
                        latest_payment.payment_date
                        or (latest_payment.paid_at.date() if latest_payment.paid_at else None)
                    ) if latest_payment else None,
                    'paid_at': latest_payment.paid_at if latest_payment else None,
                    'receipt_number': latest_payment.receipt_number if latest_payment else '',
                }
            )

    return sorted(
        rows,
        key=lambda row: (row['year'], row['month'], row['student_name'], row['course_title']),
        reverse=True,
    )


class AdminPaymentHistoryView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]

    def get(self, request):
        enrollments = Enrollment.objects.select_related(
            'student',
            'student__parent',
            'course',
        )
        rows = filter_payment_history_rows(build_payment_history_rows(enrollments), request.query_params)
        return Response(PaymentHistorySerializer(rows, many=True).data)


class MyPaymentHistoryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        enforce_student_approved(user)
        if user.role == User.ROLE_PARENT:
            enrollments = Enrollment.objects.select_related(
                'student',
                'student__parent',
                'course',
            ).filter(student__parent__user=user)
        elif user.role == User.ROLE_STUDENT:
            enrollments = Enrollment.objects.select_related(
                'student',
                'student__parent',
                'course',
            ).filter(student__user=user)
        elif user.role == User.ROLE_ADMIN:
            enrollments = Enrollment.objects.select_related(
                'student',
                'student__parent',
                'course',
            )
        else:
            enrollments = Enrollment.objects.none()
        rows = filter_payment_history_rows(build_payment_history_rows(enrollments), request.query_params)
        return Response(PaymentHistorySerializer(rows, many=True).data)


def filter_payment_history_rows(rows, params):
    search = params.get('search', '').lower()
    month = params.get('month')
    year = params.get('year')
    status = params.get('payment_status')
    student = params.get('student')
    return [
        row for row in rows
        if (not search or search in row['student_name'].lower() or search in row['course_title'].lower() or search in row['parent_name'].lower())
        and (not month or str(row['month']) == str(month))
        and (not year or str(row['year']) == str(year))
        and (not status or row['payment_status'] == status)
        and (not student or str(row['student_id']) == str(student))
    ]


class AdminPendingStudentsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]
    serializer_class = DashboardChildSerializer

    def get_queryset(self):
        return Student.objects.filter(
            approval_status=Student.STATUS_PENDING,
        ).select_related('user').prefetch_related('enrollments__course')


class AdminPendingAccountsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]
    serializer_class = PendingAccountSerializer

    def get_queryset(self):
        return User.objects.filter(
            approval_status=User.APPROVAL_PENDING,
            role__in=[User.ROLE_PARENT, User.ROLE_STUDENT],
        ).select_related('parent_profile', 'student_profile')


class AdminApproveAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]

    def post(self, request, pk):
        user = generics.get_object_or_404(
            User.objects.select_related('parent_profile', 'student_profile'),
            pk=pk,
        )
        user.approval_status = User.APPROVAL_APPROVED
        user.save(update_fields=['approval_status'])
        log_admin_action(request, 'account_approved', f'Approved account {user.email}.')

        payment = None
        invoice_created = False
        enrollment_created = False
        student = getattr(user, 'student_profile', None)
        if user.role == User.ROLE_STUDENT and student:
            student.approval_status = Student.STATUS_APPROVED
            student.save(update_fields=['approval_status', 'updated_at'])
            try:
                enrollment, enrollment_created = ensure_adult_programme_enrollment(student)
                if enrollment_created:
                    log_admin_action(
                        request,
                        'enrollment_created',
                        f'Created enrollment for {student} in {enrollment.course}.',
                    )
            except Exception:
                logger.exception('Could not create adult learner enrollment for student %s.', student.pk)
                log_admin_action(request, 'enrollment_creation_failed', f'Could not create enrollment for {student}.')
            try:
                payment, invoice_created = approval_invoice_for_student(student)
                if payment and invoice_created:
                    log_admin_action(
                        request,
                        'invoice_created',
                        f'Invoice created for {student} in {payment.enrollment.course}: {payment.receipt_number}.',
                    )
            except Exception:
                logger.exception('Could not create approval invoice for student %s.', student.pk)
                log_admin_action(request, 'invoice_creation_failed', f'Could not create invoice for {student}.')

        email_sent = False
        try:
            email_sent = send_student_approval_email(student, payment) if student else send_parent_account_approval_email(user)
            if email_sent:
                log_admin_action(request, 'approval_email_sent', f'Approval email sent for account {user.email}.')
        except Exception:
            logger.exception('Could not send account approval email for user %s.', user.pk)
            log_admin_action(request, 'approval_email_failed', f'Could not send approval email for account {user.email}.')

        return Response({
            'message': 'Account approved successfully.',
            'enrollment_created': enrollment_created,
            'invoice_created': invoice_created,
            'payment_id': payment.id if payment else None,
            'email_sent': email_sent,
            'account': PendingAccountSerializer(user).data,
        })


class AdminRejectAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]

    def post(self, request, pk):
        user = generics.get_object_or_404(User, pk=pk)
        user.approval_status = User.APPROVAL_REJECTED
        user.save(update_fields=['approval_status'])
        student = getattr(user, 'student_profile', None)
        if student:
            student.approval_status = Student.STATUS_REJECTED
            student.save(update_fields=['approval_status', 'updated_at'])
        log_admin_action(request, 'account_rejected', f'Rejected account {user.email}.')
        return Response({'message': 'Account rejected successfully.'})


class AdminApproveStudentView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]

    def post(self, request, pk):
        student = generics.get_object_or_404(
            Student.objects.select_related('parent', 'parent__user').prefetch_related('enrollments__course'),
            pk=pk,
        )
        was_already_approved = student.approval_status == Student.STATUS_APPROVED
        student.approval_status = Student.STATUS_APPROVED
        student.save(update_fields=['approval_status', 'updated_at'])
        if student.user:
            student.user.approval_status = User.APPROVAL_APPROVED
            student.user.save(update_fields=['approval_status'])
        log_admin_action(request, 'student_approved', f'Student approved: {student}.')

        enrollment_created = False
        try:
            enrollment, enrollment_created = ensure_adult_programme_enrollment(student)
            if enrollment_created:
                log_admin_action(
                    request,
                    'enrollment_created',
                    f'Created enrollment for {student} in {enrollment.course}.',
                )
        except Exception:
            logger.exception('Could not create adult learner enrollment for student %s.', student.pk)
            log_admin_action(request, 'enrollment_creation_failed', f'Could not create enrollment for {student}.')

        payment = None
        invoice_created = False
        try:
            payment, invoice_created = approval_invoice_for_student(student)
            if payment and invoice_created:
                log_admin_action(
                    request,
                    'invoice_created',
                    f'Invoice created for {student} in {payment.enrollment.course}: {payment.receipt_number}.',
                )
        except Exception:
            logger.exception('Could not create approval invoice for student %s.', student.pk)
            log_admin_action(request, 'invoice_creation_failed', f'Could not create invoice for {student}.')

        email_sent = False
        if not was_already_approved or invoice_created:
            try:
                email_sent = send_student_approval_email(student, payment)
                if email_sent:
                    log_admin_action(request, 'approval_email_sent', f'Approval email sent for {student}.')
            except Exception:
                logger.exception('Could not send approval email for student %s.', student.pk)
                log_admin_action(request, 'approval_email_failed', f'Could not send approval email for {student}.')

        if payment and invoice_created:
            try:
                send_admin_invoice_notification(student, payment)
            except Exception:
                logger.exception('Could not send admin invoice notification for student %s.', student.pk)

        if student.parent and student.parent.user and (not was_already_approved or invoice_created):
            Notification.objects.create(
                title='Child approved',
                message=(
                    f'Your child {student} has been approved by Velttech Coding Academy.'
                    + (' A pending invoice is ready in your payment portal.' if payment else '')
                ),
                audience=Notification.AUDIENCE_PARENTS,
                recipient=student.parent.user,
            )
        elif student.user and (not was_already_approved or invoice_created):
            Notification.objects.create(
                title='Enrollment approved',
                message=(
                    'Your Velttech Coding Academy enrollment has been approved.'
                    + (' A pending invoice is ready in your payment portal.' if payment else '')
                ),
                audience=Notification.AUDIENCE_STUDENTS,
                recipient=student.user,
            )
        return Response(
            {
                'message': 'Student approved successfully.',
                'enrollment_created': enrollment_created,
                'invoice_created': invoice_created,
                'payment_id': payment.id if payment else None,
                'email_sent': email_sent,
                'student': DashboardChildSerializer(student).data,
            }
        )


class AdminRejectStudentView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]

    def post(self, request, pk):
        student = generics.get_object_or_404(Student, pk=pk)
        student.approval_status = Student.STATUS_REJECTED
        student.save(update_fields=['approval_status', 'updated_at'])
        if student.user:
            student.user.approval_status = User.APPROVAL_REJECTED
            student.user.save(update_fields=['approval_status'])
        if student.parent and student.parent.user:
            Notification.objects.create(
                title='Child not approved',
                message=f'Your child {student} was not approved. Please contact the academy.',
                audience=Notification.AUDIENCE_PARENTS,
                recipient=student.parent.user,
            )
        log_admin_action(request, 'student_rejected', f'Rejected student {student}.')
        return Response(DashboardChildSerializer(student).data)


class AdminEnrollmentCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]
    serializer_class = EnrollmentSerializer

    def perform_create(self, serializer):
        enrollment = serializer.save()
        log_admin_action(self.request, 'enrollment_created', f'Created enrollment for {enrollment.student} in {enrollment.course}.')
        if enrollment.student.approval_status != Student.STATUS_APPROVED:
            return

        payment = None
        invoice_created = False
        try:
            with transaction.atomic():
                payment, invoice_created = create_pending_invoice_for_enrollment(enrollment)
            if invoice_created:
                log_admin_action(
                    self.request,
                    'invoice_created',
                    f'Invoice created for {enrollment.student} in {enrollment.course}: {payment.receipt_number}.',
                )
        except Exception:
            logger.exception('Could not create enrollment invoice for enrollment %s.', enrollment.pk)
            log_admin_action(self.request, 'invoice_creation_failed', f'Could not create invoice for {enrollment.student}.')
            return

        if invoice_created:
            try:
                email_sent = send_student_approval_email(enrollment.student, payment)
                if email_sent:
                    log_admin_action(self.request, 'approval_email_sent', f'Approval email sent for {enrollment.student}.')
            except Exception:
                logger.exception('Could not send invoice email for student %s.', enrollment.student_id)
                log_admin_action(self.request, 'approval_email_failed', f'Could not send approval email for {enrollment.student}.')
            try:
                send_admin_invoice_notification(enrollment.student, payment)
            except Exception:
                logger.exception('Could not send admin invoice notification for student %s.', enrollment.student_id)


class AdminActivityLogView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminUserRole]
    serializer_class = ActivityLogSerializer

    def get_queryset(self):
        queryset = ActivityLog.objects.select_related('user')
        search = self.request.query_params.get('search')
        action = self.request.query_params.get('action')
        if search:
            queryset = queryset.filter(Q(user__email__icontains=search) | Q(description__icontains=search))
        if action:
            queryset = queryset.filter(action__icontains=action)
        return queryset


def instructor_enrollments_for(user):
    return Enrollment.objects.select_related(
        'student',
        'student__parent',
        'course',
    ).filter(instructor=user)


class InstructorDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsInstructorUserRole]

    def get(self, request):
        enrollments = instructor_enrollments_for(request.user)
        courses = enrollments.values('course').distinct().count()
        students = enrollments.values('student').distinct().count()
        active_enrollments = enrollments.filter(status=Enrollment.STATUS_ACTIVE).count()
        recent_enrollments = enrollments.order_by('-created_at')[:5]
        notifications = visible_notifications_for(request.user)[:5]

        return Response(
            {
                'total_assigned_courses': courses,
                'total_assigned_students': students,
                'active_enrollments': active_enrollments,
                'recent_enrollments': InstructorEnrollmentSerializer(
                    recent_enrollments,
                    many=True,
                ).data,
                'notifications': DashboardNotificationSerializer(
                    notifications,
                    many=True,
                ).data,
            }
        )


class InstructorCoursesView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsInstructorUserRole]
    serializer_class = InstructorCourseSerializer

    def get_queryset(self):
        return Course.objects.filter(
            enrollments__instructor=self.request.user,
        ).annotate(
            assigned_students_count=Count(
                'enrollments__student',
                filter=Q(enrollments__instructor=self.request.user),
                distinct=True,
            )
        ).distinct()


class InstructorStudentsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsInstructorUserRole]
    serializer_class = InstructorStudentSerializer

    def get_queryset(self):
        enrollments = instructor_enrollments_for(self.request.user)
        enrollment_map = {
            enrollment.student_id: enrollment
            for enrollment in enrollments.order_by('-created_at')
        }
        students = list(
            Student.objects.filter(
                enrollments__instructor=self.request.user,
            ).select_related('parent').distinct()
        )
        for student in students:
            student.instructor_enrollment = enrollment_map.get(student.id)
        return students


class InstructorEnrollmentListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsInstructorUserRole]
    serializer_class = InstructorEnrollmentSerializer

    def get_queryset(self):
        return instructor_enrollments_for(self.request.user)


class InstructorNotificationsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsInstructorUserRole]
    serializer_class = DashboardNotificationSerializer

    def get_queryset(self):
        return visible_notifications_for(self.request.user)


class InstructorAttendanceView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsInstructorUserRole]
    serializer_class = AttendanceSerializer

    def get_queryset(self):
        return Attendance.objects.select_related(
            'enrollment',
            'enrollment__student',
            'enrollment__course',
        ).filter(enrollment__instructor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)


class InstructorLessonNotesView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsInstructorUserRole]
    serializer_class = LessonNoteSerializer

    def get_queryset(self):
        return LessonNote.objects.select_related(
            'course',
            'instructor',
        ).filter(instructor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(instructor=self.request.user)


class InstructorProgressReportsView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsInstructorUserRole]
    serializer_class = ProgressReportSerializer

    def get_queryset(self):
        return ProgressReport.objects.select_related(
            'enrollment',
            'enrollment__student',
            'enrollment__course',
        ).filter(enrollment__instructor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class InstructorAssignmentsView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsInstructorUserRole]
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        return Assignment.objects.select_related(
            'course',
            'instructor',
        ).filter(instructor=self.request.user)

    def perform_create(self, serializer):
        serializer.save(instructor=self.request.user)


class InstructorSubmissionsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsInstructorUserRole]
    serializer_class = AssignmentSubmissionSerializer

    def get_queryset(self):
        return AssignmentSubmission.objects.select_related(
            'assignment',
            'assignment__course',
            'student',
        ).filter(assignment__instructor=self.request.user)


class InstructorGradeSubmissionView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsInstructorUserRole]
    serializer_class = GradeAssignmentSubmissionSerializer
    http_method_names = ['patch']

    def get_queryset(self):
        return AssignmentSubmission.objects.select_related(
            'assignment',
            'assignment__course',
            'student',
        ).filter(assignment__instructor=self.request.user)

    def perform_update(self, serializer):
        serializer.save(status=AssignmentSubmission.STATUS_GRADED)


class MyAttendanceView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AttendanceSerializer

    def get_queryset(self):
        enforce_student_approved(self.request.user)
        queryset = Attendance.objects.select_related(
            'enrollment',
            'enrollment__student',
            'enrollment__course',
        )
        user = self.request.user
        if user.role == User.ROLE_ADMIN:
            return queryset
        if user.role == User.ROLE_PARENT:
            return queryset.filter(enrollment__student__parent__user=user)
        if user.role == User.ROLE_STUDENT:
            return queryset.filter(enrollment__student__user=user)
        return queryset.none()


class MyProgressView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProgressReportSerializer

    def get_queryset(self):
        enforce_student_approved(self.request.user)
        queryset = ProgressReport.objects.select_related(
            'enrollment',
            'enrollment__student',
            'enrollment__course',
        )
        user = self.request.user
        if user.role == User.ROLE_ADMIN:
            return queryset
        if user.role == User.ROLE_PARENT:
            return queryset.filter(enrollment__student__parent__user=user)
        if user.role == User.ROLE_STUDENT:
            return queryset.filter(enrollment__student__user=user)
        return queryset.none()


class MyAssignmentsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MyAssignmentSerializer

    def get_queryset(self):
        user = self.request.user
        enforce_student_approved(user)
        queryset = Assignment.objects.select_related('course', 'instructor').filter(
            is_active=True,
        )

        if user.role == User.ROLE_ADMIN:
            visible_submissions = AssignmentSubmission.objects.select_related('student')
            return queryset.prefetch_related(
                Prefetch('submissions', queryset=visible_submissions, to_attr='visible_submissions')
            )

        if user.role == User.ROLE_PARENT:
            visible_submissions = AssignmentSubmission.objects.select_related('student').filter(
                student__parent__user=user,
            )
            return queryset.filter(
                course__enrollments__student__parent__user=user,
            ).distinct().prefetch_related(
                Prefetch('submissions', queryset=visible_submissions, to_attr='visible_submissions')
            )

        if user.role == User.ROLE_STUDENT:
            visible_submissions = AssignmentSubmission.objects.filter(
                student__user=user,
            )
            return queryset.filter(
                course__enrollments__student__user=user,
            ).distinct().prefetch_related(
                Prefetch('submissions', queryset=visible_submissions, to_attr='visible_submissions')
            )

        return queryset.none()


class SubmitAssignmentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        user = request.user
        enforce_student_approved(user)
        if user.role != User.ROLE_STUDENT:
            raise PermissionDenied('Only students can submit assignments.')

        assignment = generics.get_object_or_404(
            Assignment.objects.filter(
                is_active=True,
                course__enrollments__student__user=user,
            ).distinct(),
            pk=pk,
        )
        student = getattr(user, 'student_profile', None)
        if not student:
            raise PermissionDenied('Student profile is required before submitting assignments.')

        submission, _ = AssignmentSubmission.objects.get_or_create(
            assignment=assignment,
            student=student,
        )
        if submission.status == AssignmentSubmission.STATUS_GRADED:
            raise PermissionDenied('Graded assignments cannot be resubmitted.')

        serializer = AssignmentSubmissionSerializer(
            submission,
            data={'submission_text': request.data.get('submission_text', '')},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(
            submitted_at=timezone.now(),
            status=AssignmentSubmission.STATUS_SUBMITTED,
        )
        return Response(serializer.data)
