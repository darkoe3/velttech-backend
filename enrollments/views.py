from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from .models import Enrollment
from .serializers import EnrollmentSerializer
from users.permissions import IsAdminOrReadOnly


class EnrollmentViewSet(viewsets.ModelViewSet):
    queryset = Enrollment.objects.select_related(
        'student',
        'student__parent',
        'course',
        'instructor',
    )
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if user.role == 'admin':
            search = self.request.query_params.get('search')
            status = self.request.query_params.get('status')
            course = self.request.query_params.get('course')
            instructor = self.request.query_params.get('instructor')
            if search:
                queryset = queryset.filter(
                    Q(student__first_name__icontains=search)
                    | Q(student__last_name__icontains=search)
                    | Q(course__title__icontains=search)
                )
            if status:
                queryset = queryset.filter(status=status)
            if course:
                queryset = queryset.filter(course_id=course)
            if instructor:
                queryset = queryset.filter(instructor_id=instructor)
            return queryset
        if user.role == 'parent':
            return queryset.filter(student__parent__user=user)
        if user.role == 'student':
            return queryset.filter(student__user=user)
        if user.role == 'instructor':
            return queryset.filter(instructor=user)
        return queryset.none()

    def perform_create(self, serializer):
        enrollment = serializer.save()
        from users.views import log_admin_action
        if self.request.user.role == 'admin':
            log_admin_action(self.request, 'enrollment_created', f'Created enrollment for {enrollment.student} in {enrollment.course}.')
