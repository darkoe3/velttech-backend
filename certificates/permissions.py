from rest_framework.permissions import BasePermission, SAFE_METHODS


class CanIssueCertificate(BasePermission):
    """
    Allow admin to issue any certificate.
    Allow instructor to issue certificate for their enrolled courses.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Admin can do anything
        if request.user.role == 'admin':
            return True

        # Instructor can issue certificates
        if request.user.role == 'instructor':
            return True

        return False

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True

        if request.user.role == 'instructor':
            # Instructor can only issue for their enrolled courses
            return obj.enrollment.instructor == request.user

        return False


class CanViewCertificate(BasePermission):
    """
    Admin can view all certificates.
    Instructor can view certificates for their courses.
    Student can view own certificates.
    Parent can view certificates for their children.
    Public can verify certificate with verification code.
    """

    def has_permission(self, request, view):
        # Allow unauthenticated users to verify with code
        if view.action == 'verify':
            return True

        if not request.user or not request.user.is_authenticated:
            return False

        return True

    def has_object_permission(self, request, view, obj):
        user = request.user

        # Admin can view all
        if user.role == 'admin':
            return True

        # Instructor can view certificates for their courses
        if user.role == 'instructor':
            return obj.enrollment.instructor == user

        # Student can view own certificates
        if user.role == 'student':
            return obj.student.user == user

        # Parent can view certificates for their children
        if user.role == 'parent':
            return obj.student.parent.user == user

        return False


class CanRevokeCertificate(BasePermission):
    """Only admin can revoke certificates"""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'admin'
        )

    def has_object_permission(self, request, view, obj):
        return request.user.role == 'admin'
