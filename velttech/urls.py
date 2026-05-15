"""
URL configuration for velttech project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from django.http import JsonResponse
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from courses.views import CourseViewSet
from enrollments.views import EnrollmentViewSet
from payments.views import PaymentViewSet
from students.views import ParentViewSet, StudentViewSet
from users.views import (
    AdminApproveStudentView,
    AdminEnrollmentCreateView,
    AdminPaymentHistoryView,
    AdminPendingStudentsView,
    AdminRejectStudentView,
    DashboardView,
    ChangePasswordView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    AdminActivityLogView,
    LoginView,
    LogoutView,
    MeView,
    MyChildrenView,
    MyCoursesView,
    MyPaymentsView,
    MyPaymentHistoryView,
    RegisterView,
    InstructorCoursesView,
    InstructorDashboardView,
    InstructorAttendanceView,
    InstructorEnrollmentListView,
    InstructorLessonNotesView,
    InstructorNotificationsView,
    InstructorProgressReportsView,
    InstructorAssignmentsView,
    InstructorSubmissionsView,
    InstructorGradeSubmissionView,
    InstructorStudentsView,
    MyAssignmentsView,
    MyAttendanceView,
    MyProgressView,
    SubmitAssignmentView,
)
from notifications.views import NotificationViewSet

router = DefaultRouter()
router.register('parents', ParentViewSet, basename='parent')
router.register('students', StudentViewSet, basename='student')
router.register('courses', CourseViewSet, basename='course')
router.register('enrollments', EnrollmentViewSet, basename='enrollment')
router.register('payments', PaymentViewSet, basename='payment')
router.register('notifications', NotificationViewSet, basename='notification')


def api_root(request):
    return JsonResponse(
        {
            'message': 'Velttech Coding Academy API',
            'auth': {
                'register': '/api/auth/register/',
                'login': '/api/auth/login/',
                'logout': '/api/auth/logout/',
                'me': '/api/auth/me/',
            },
            'resources': {
                'dashboard': '/api/dashboard/',
                'my_courses': '/api/my-courses/',
                'my_children': '/api/my-children/',
                'my_payments': '/api/my-payments/',
                'my_assignments': '/api/my-assignments/',
                'students': '/api/students/',
                'courses': '/api/courses/',
                'enrollments': '/api/enrollments/',
                'payments': '/api/payments/',
                'notifications': '/api/notifications/',
            },
        }
    )

urlpatterns = [
    path('', api_root, name='api_root'),
    path('admin/', admin.site.urls),
    path('api/auth/register/', RegisterView.as_view(), name='register'),
    path('api/auth/login/', LoginView.as_view(), name='token_obtain_pair'),
    path('api/auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/auth/logout/', LogoutView.as_view(), name='token_blacklist'),
    path('api/auth/me/', MeView.as_view(), name='me'),
    path('api/auth/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('api/auth/password-reset/request/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('api/auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    path('api/dashboard/', DashboardView.as_view(), name='dashboard'),
    path('api/my-courses/', MyCoursesView.as_view(), name='my_courses'),
    path('api/my-children/', MyChildrenView.as_view(), name='my-children'),
    path('api/my-payments/', MyPaymentsView.as_view(), name='my_payments'),
    path('api/my-payments/history/', MyPaymentHistoryView.as_view(), name='my_payments_history'),
    path('api/my-attendance/', MyAttendanceView.as_view(), name='my_attendance'),
    path('api/my-progress/', MyProgressView.as_view(), name='my_progress'),
    path('api/my-assignments/', MyAssignmentsView.as_view(), name='my_assignments'),
    path('api/my-assignments/<int:pk>/submit/', SubmitAssignmentView.as_view(), name='submit_assignment'),
    path('api/admin/pending-students/', AdminPendingStudentsView.as_view(), name='admin-pending-students'),
    path('api/admin/students/<int:pk>/approve/', AdminApproveStudentView.as_view(), name='admin-approve-student'),
    path('api/admin/students/<int:pk>/reject/', AdminRejectStudentView.as_view(), name='admin-reject-student'),
    path('api/admin/enrollments/', AdminEnrollmentCreateView.as_view(), name='admin-enrollments'),
    path('api/admin/payments/history/', AdminPaymentHistoryView.as_view(), name='admin-payment-history'),
    path('api/admin/activity-logs/', AdminActivityLogView.as_view(), name='admin-activity-logs'),
    path('api/instructor/dashboard/', InstructorDashboardView.as_view(), name='instructor-dashboard'),
    path('api/instructor/courses/', InstructorCoursesView.as_view(), name='instructor-courses'),
    path('api/instructor/students/', InstructorStudentsView.as_view(), name='instructor-students'),
    path('api/instructor/enrollments/', InstructorEnrollmentListView.as_view(), name='instructor-enrollments'),
    path('api/instructor/notifications/', InstructorNotificationsView.as_view(), name='instructor-notifications'),
    path('api/instructor/attendance/', InstructorAttendanceView.as_view(), name='instructor-attendance'),
    path('api/instructor/lesson-notes/', InstructorLessonNotesView.as_view(), name='instructor-lesson-notes'),
    path('api/instructor/progress-reports/', InstructorProgressReportsView.as_view(), name='instructor-progress-reports'),
    path('api/instructor/assignments/', InstructorAssignmentsView.as_view(), name='instructor-assignments'),
    path('api/instructor/submissions/', InstructorSubmissionsView.as_view(), name='instructor-submissions'),
    path('api/instructor/submissions/<int:pk>/grade/', InstructorGradeSubmissionView.as_view(), name='instructor-grade-submission'),
    path('api/', include(router.urls)),
]
