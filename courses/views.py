from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Course
from .serializers import CourseSerializer
from users.permissions import IsAdminOrReadOnly


class CourseViewSet(viewsets.ModelViewSet):
    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = [IsAuthenticated, IsAdminOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        queryset = super().get_queryset()
        if user.role == 'admin':
            return queryset
        if user.role == 'parent':
            return queryset.filter(enrollments__student__parent__user=user).distinct()
        if user.role == 'student':
            return queryset.filter(enrollments__student__user=user).distinct()
        return queryset.none()

    def perform_create(self, serializer):
        course = serializer.save()
        from users.views import log_admin_action
        if self.request.user.role == 'admin':
            log_admin_action(self.request, 'course_created', f'Created course {course.title}.')

    def perform_update(self, serializer):
        course = serializer.save()
        from users.views import log_admin_action
        if self.request.user.role == 'admin':
            log_admin_action(self.request, 'course_updated', f'Updated course {course.title}.')
